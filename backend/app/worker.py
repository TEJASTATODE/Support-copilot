"""arq background worker.

Jobs:
1. ingest_document  — chunk + embed KB documents (triggered on upload)
2. auto_triage      — classify + route new tickets (runs on schedule)
3. check_sla        — flag breached tickets (runs on schedule)
"""
import asyncio
import selectors
import sys
from arq import cron
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.DefaultEventLoopPolicy())
    asyncio.set_event_loop(asyncio.SelectorEventLoop(selectors.SelectSelector()))

from arq.connections import RedisSettings
from app.config import settings
from app.db import init_db, close_db, get_pool
from app.chunking import chunk_text
from app.embeddings import aembed_passages


# ── Job 1: Document ingestion ─────────────────────────────────────────────────

async def ingest_document(ctx, document_id: int) -> dict:
    """Chunk → embed → store. Marks the document ready or failed."""
    pool = get_pool()
    async with pool.connection() as conn:
        doc = await (await conn.execute(
            "SELECT content FROM documents WHERE id = %s",
            (document_id,),
        )).fetchone()

        if not doc:
            return {"error": "document not found"}

        try:
            chunks = chunk_text(doc["content"])
            embeddings = await aembed_passages(chunks)
            for i, (text, vec) in enumerate(zip(chunks, embeddings)):
                await conn.execute(
                    "INSERT INTO chunks (document_id, chunk_index, content, embedding) VALUES (%s, %s, %s, %s)",
                    (document_id, i, text, vec),
                )
            await conn.execute(
                "UPDATE documents SET status = 'ready', chunk_count = %s WHERE id = %s",
                (len(chunks), document_id),
            )
            print(f"[worker] doc {document_id} ingested — {len(chunks)} chunks")
            return {"document_id": document_id, "chunks": len(chunks)}
        except Exception as e:
            await conn.execute(
                "UPDATE documents SET status = 'failed' WHERE id = %s",
                (document_id,)
            )
            raise e


# ── Job 2: Auto-triage ────────────────────────────────────────────────────────

async def auto_triage(ctx) -> dict:
    """
    Classify and route new/unclassified tickets using the LLM.

    Why this runs in the background and not in the request handler:
    - It processes ALL pending tickets in one batch run
    - It runs on a schedule — even when no operator is logged in
    - LLM classification takes time — can't block a request
    - This is what makes the system PROACTIVE, not just reactive

    Flow:
    1. Fetch all tickets with status='new' and no intent set
    2. For each ticket, ask the LLM to classify intent + urgency
    3. Update the ticket with the classification
    4. Route to the right queue (billing, shipping, general)
    """
    from app.llm import complete

    pool = get_pool()
    async with pool.connection() as conn:
        # fetch unclassified tickets
        tickets = await (await conn.execute(
            """
            SELECT id, subject, body, customer_id
            FROM tickets
            WHERE (intent IS NULL OR intent = '')
              AND status = 'new'
            ORDER BY created_at ASC
            LIMIT 20
            """,
        )).fetchall()

    if not tickets:
        print("[triage] no new tickets to classify")
        return {"classified": 0}

    print(f"[triage] classifying {len(tickets)} tickets")
    classified = 0

    for ticket in tickets:
        try:
            body = ticket["body"] or ticket["subject"] or ""
            if not body.strip():
                continue

            # LLM classification
            result = await complete(
                system=(
                    "You are a customer support ticket classifier.\n"
                    "Classify the ticket into:\n\n"
                    "INTENT (pick one):\n"
                    "- refund: customer wants money back\n"
                    "- shipping: delivery or tracking issue\n"
                    "- product: product quality or defect\n"
                    "- account: account or login issue\n"
                    "- billing: payment or invoice issue\n"
                    "- complaint: general complaint\n"
                    "- inquiry: general question\n"
                    "- other: doesn't fit above\n\n"
                    "URGENCY (pick one):\n"
                    "- high: angry customer, legal threat, payment issue\n"
                    "- medium: needs resolution soon\n"
                    "- low: general question, no urgency\n\n"
                    "TEAM (pick one):\n"
                    "- billing: refund, payment, invoice\n"
                    "- logistics: shipping, delivery, tracking\n"
                    "- support: everything else\n\n"
                    "Reply in EXACT format:\n"
                    "INTENT: <intent>\n"
                    "URGENCY: <urgency>\n"
                    "TEAM: <team>\n"
                    "SUMMARY: <one sentence summary>\n\n"
                    "No extra text."
                ),
                user=f"Ticket:\n{body[:500]}",
                temperature=0.0,
            )

            # parse result
            intent = "other"
            urgency = "medium"
            team = "support"
            summary = ""

            for line in result.strip().split("\n"):
                if line.startswith("INTENT:"):
                    intent = line.split(":", 1)[1].strip().lower()
                elif line.startswith("URGENCY:"):
                    urgency = line.split(":", 1)[1].strip().lower()
                elif line.startswith("TEAM:"):
                    team = line.split(":", 1)[1].strip().lower()
                elif line.startswith("SUMMARY:"):
                    summary = line.split(":", 1)[1].strip()

            # update ticket
            pool2 = get_pool()
            async with pool2.connection() as conn2:
                await conn2.execute(
                    """
                    UPDATE tickets
                    SET intent = %s,
                        urgency = %s,
                        assigned_to = %s,
                        subject = COALESCE(NULLIF(subject, ''), %s),
                        status = 'open'
                    WHERE id = %s
                    """,
                    (intent, urgency, team, summary, ticket["id"]),
                )

            print(f"[triage] ticket {ticket['id']} → intent={intent} urgency={urgency} team={team}")
            classified += 1

        except Exception as e:
            print(f"[triage] failed to classify ticket {ticket['id']}: {e}")

    return {"classified": classified}


# ── Job 3: SLA breach detection ───────────────────────────────────────────────

async def check_sla(ctx) -> dict:
    """
    Flag tickets that have breached SLA (open too long without resolution).

    SLA thresholds:
    - high urgency: 1 hour
    - medium urgency: 4 hours
    - low urgency: 24 hours

    Why this matters: SLA tracking is what makes a support system
    accountable. Without it, tickets can sit open for days unnoticed.
    This job surfaces breaches in the Metrics page.
    """
    pool = get_pool()
    async with pool.connection() as conn:
        # flag high urgency tickets open more than 1 hour
        await conn.execute(
            """
            UPDATE tickets
            SET sla_breached = true
            WHERE status = 'open'
              AND urgency = 'high'
              AND sla_breached = false
              AND created_at < now() - interval '1 hour'
            """
        )

        # flag medium urgency tickets open more than 4 hours
        await conn.execute(
            """
            UPDATE tickets
            SET sla_breached = true
            WHERE status = 'open'
              AND urgency = 'medium'
              AND sla_breached = false
              AND created_at < now() - interval '4 hours'
            """
        )

        # flag low urgency tickets open more than 24 hours
        await conn.execute(
            """
            UPDATE tickets
            SET sla_breached = true
            WHERE status = 'open'
              AND urgency = 'low'
              AND sla_breached = false
              AND created_at < now() - interval '24 hours'
            """
        )

        # count breaches
        breached = await (await conn.execute(
            "SELECT COUNT(*) as count FROM tickets WHERE sla_breached = true AND status = 'open'"
        )).fetchone()

    count = breached["count"] if breached else 0
    print(f"[sla] {count} tickets currently breaching SLA")
    return {"breached": count}


# ── Lifecycle ─────────────────────────────────────────────────────────────────

async def on_startup(ctx):
    await init_db()
    print("[worker] started, DB pool open")


async def on_shutdown(ctx):
    await close_db()
    print("[worker] shutting down")


# ── Worker settings ───────────────────────────────────────────────────────────
class WorkerSettings:
    functions = [ingest_document, auto_triage, check_sla]
    on_startup = on_startup
    on_shutdown = on_shutdown
    redis_settings = RedisSettings.from_dsn(settings.redis_url)

    cron_jobs = [
        cron(auto_triage, minute={0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55}),
        cron(check_sla,   minute={0, 15, 30, 45}),
    ]
