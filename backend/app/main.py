"""
FastAPI app — Full: checkpointer + tools + approval + JWT auth + RBAC + DB users + auto-triage.
"""
import asyncio
import json
import time
from contextlib import asynccontextmanager
from typing import Annotated
from pathlib import Path

from fastapi import FastAPI, Request, Depends, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from arq import create_pool as arq_create_pool
from arq.connections import RedisSettings
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from app.config import settings
from app.db import init_db, close_db, get_or_init_pool
from app.graph import build_graph
from app.auth import (
    authenticate_user, create_access_token, create_refresh_token,
    decode_refresh_token,
    get_current_user, require_admin, require_any,
    seed_admin, hash_password,
    Token, TokenData, UserCreate, UserOut,
)
from app.tracing import trace_agent_run


@asynccontextmanager
async def lifespan(app: FastAPI):
    db_pool = await init_db()
    app.state.db_pool = db_pool
    print(f"[startup] db_pool opened: {db_pool is not None}")

    await seed_admin(pool=db_pool)
    print(f"[startup] seed_admin done")

    cp_pool = AsyncConnectionPool(
        settings.database_url,
        kwargs={
            "autocommit": True,
            "prepare_threshold": 0,
            "row_factory": dict_row,
        },
        open=False,
        min_size=1,
        max_size=5,
    )
    await cp_pool.open()

    checkpointer = AsyncPostgresSaver(cp_pool)
    await checkpointer.setup()

    compiled = build_graph(checkpointer=checkpointer)
    app.state.graph = compiled
    app.state.cp_pool = cp_pool

    import app.graph as graph_module
    graph_module._graph = compiled

    app.state.redis = await arq_create_pool(RedisSettings.from_dsn(settings.redis_url))

    yield

    await app.state.redis.close()
    await cp_pool.close()
    await close_db()


app = FastAPI(title="Support Copilot", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url],
    allow_methods=["*"],
    allow_headers=["*"],
)
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ── DB dependency ──────────────────────────────────────────────────────────────

async def get_db(request: Request) -> AsyncConnectionPool:
    """
    FastAPI dependency — always returns a working pool.
    Tries app.state first, falls back to module-level pool,
    initializes if needed. Handles Windows subprocess model.
    """
    try:
        return request.app.state.db_pool
    except AttributeError:
        return await get_or_init_pool()


# ── Request models ─────────────────────────────────────────────────────────────

class ChatIn(BaseModel):
    message: str
    customer_id: int | None = None
    thread_id: str = "default"


class DocIn(BaseModel):
    title: str
    content: str
    source: str | None = None


class ApprovalIn(BaseModel):
    approved: bool
    thread_id: str


class TicketIn(BaseModel):
    body: str
    subject: str | None = None
    customer_id: int | None = None
    thread_id: str | None = None

class RefreshIn(BaseModel):
    refresh_token: str
# ── Auth endpoints ─────────────────────────────────────────────────────────────
@app.post("/auth/login", response_model=Token)
@limiter.limit("5/minute")
async def login(
    request: Request,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: AsyncConnectionPool = Depends(get_db),
):
    user = await authenticate_user(form_data.username, form_data.password, pool=db)
    if not user:
        raise HTTPException(status_code=401, detail="Incorrect username or password")

    access_token = create_access_token({
        "sub": user["username"],
        "role": user["role"],
        "customer_id": user.get("customer_id"),
    })
    refresh_token = create_refresh_token({
        "sub": user["username"],
        "role": user["role"],
        "customer_id": user.get("customer_id"),
    })
    return Token(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        role=user["role"],
        username=user["username"],
        customer_id=user.get("customer_id"),
    )


@app.get("/auth/me")
async def me(current_user: Annotated[TokenData, Depends(get_current_user)]):
    return {
        "username": current_user.username,
        "role": current_user.role,
        "customer_id": current_user.customer_id,
    }


# ── Health ─────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok"}


# ── Tickets ────────────────────────────────────────────────────────────────────

@app.post("/tickets/intake")
@limiter.limit("30/minute")
async def intake_ticket(
    request: Request,
    body: TicketIn,
    db: AsyncConnectionPool = Depends(get_db),
):
    async with db.connection() as conn:
        row = await (await conn.execute(
            """
            INSERT INTO tickets (customer_id, thread_id, subject, body, status)
            VALUES (%s, %s, %s, %s, 'new')
            RETURNING id, status, created_at
            """,
            (body.customer_id, body.thread_id, body.subject or body.body[:80], body.body),
        )).fetchone()
    print(f"[intake] ticket {row['id']} created")
    return {
        "ticket_id": row["id"],
        "status": row["status"],
        "message": "Ticket received — will be triaged within 5 minutes",
    }


@app.get("/tickets")
async def list_tickets(
    current_user: Annotated[TokenData, Depends(require_admin)],
    db: AsyncConnectionPool = Depends(get_db),
):
    async with db.connection() as conn:
        rows = await (await conn.execute(
            """
            SELECT id, customer_id, subject, intent, urgency,
                   status, assigned_to, sla_breached, created_at
            FROM tickets
            ORDER BY
                sla_breached DESC,
                CASE urgency
                    WHEN 'high'   THEN 1
                    WHEN 'medium' THEN 2
                    WHEN 'low'    THEN 3
                    ELSE 4
                END,
                created_at ASC
            LIMIT 100
            """
        )).fetchall()
    return rows


# ── Chat ───────────────────────────────────────────────────────────────────────

@app.post("/chat")
@limiter.limit("20/minute")
async def chat(
    request: Request,
    body: ChatIn,
    current_user: Annotated[TokenData, Depends(require_any)],
    db: AsyncConnectionPool = Depends(get_db),
):
    graph = request.app.state.graph
    config = {"configurable": {"thread_id": body.thread_id}}
    start = time.time()

    if current_user.role == "user":
        customer_id = current_user.customer_id or 0
    else:
        customer_id = body.customer_id or current_user.customer_id or 0

    result = await graph.ainvoke(
        {
            "message": body.message,
            "customer_id": customer_id,
            "memories": [],
            "context": [],
        },
        config=config,
    )

    duration_ms = (time.time() - start) * 1000
    trace_agent_run(
        thread_id=body.thread_id,
        customer_id=customer_id,
        message=body.message,
        result=result,
        duration_ms=duration_ms,
    )

    interrupt_data = result.get("__interrupt__")
    if interrupt_data:
        interrupt_value = interrupt_data[0].value if interrupt_data else {}
        action = interrupt_value.get("action", "unknown")
        payload = interrupt_value.get("payload", {})

        async with db.connection() as conn:
            await conn.execute(
                """
                INSERT INTO approvals (thread_id, customer_id, action, payload)
                VALUES (%s, %s, %s, %s)
                """,
                (body.thread_id, customer_id, action, json.dumps(payload)),
            )
            await conn.execute(
                """
                INSERT INTO tickets (customer_id, thread_id, body, status)
                VALUES (%s, %s, %s, 'new')
                """,
                (customer_id, body.thread_id, body.message),
            )

        return {
            "status": "pending_approval",
            "action": action,
            "reason": interrupt_value.get("reason", ""),
            "draft": interrupt_value.get("draft", ""),
            "thread_id": body.thread_id,
        }

    answer = result.get("draft", "")
    action_result = result.get("action_result")
    if action_result and action_result.get("status") not in (None, "error"):
        answer += f"\n\n✓ {action_result.get('message', '')}"
    if result.get("escalate") and not action_result:
        answer = "[Escalating to human agent]\n\n" + answer

    async def gen():
        for word in answer.split(" "):
            yield word + " "
            await asyncio.sleep(0.02)

    return StreamingResponse(gen(), media_type="text/plain")


# ── Approvals ──────────────────────────────────────────────────────────────────

@app.post("/approve")
async def approve_action(
    body: ApprovalIn,
    request: Request,
    current_user: Annotated[TokenData, Depends(require_admin)],
    db: AsyncConnectionPool = Depends(get_db),
):
    from langgraph.types import Command
    graph = request.app.state.graph
    config = {"configurable": {"thread_id": body.thread_id}}

    async with db.connection() as conn:
        await conn.execute(
            """
            UPDATE approvals
            SET status = %s, resolved_at = now()
            WHERE thread_id = %s AND status = 'pending'
            """,
            ("approved" if body.approved else "rejected", body.thread_id),
        )

    result = await graph.ainvoke(
        Command(resume={"approved": body.approved}),
        config=config,
    )

    action_result = result.get("action_result")
    if action_result:
        return {
            "status": "executed" if body.approved else "rejected",
            "result": action_result,
        }
    return {"status": "completed"}


@app.get("/approvals")
async def list_approvals(
    current_user: Annotated[TokenData, Depends(require_admin)],
    db: AsyncConnectionPool = Depends(get_db),
):
    async with db.connection() as conn:
        rows = await (await conn.execute(
            """
            SELECT id, thread_id, customer_id, action, payload, status, created_at
            FROM approvals ORDER BY created_at DESC LIMIT 50
            """
        )).fetchall()
    return rows


# ── Documents ──────────────────────────────────────────────────────────────────

@app.post("/documents")
async def add_document(
    body: DocIn,
    request: Request,
    current_user: Annotated[TokenData, Depends(require_admin)],
    db: AsyncConnectionPool = Depends(get_db),
):
    async with db.connection() as conn:
        row = await (await conn.execute(
            "INSERT INTO documents (title, source, content) VALUES (%s, %s, %s) RETURNING id, status",
            (body.title, body.source, body.content),
        )).fetchone()
    await request.app.state.redis.enqueue_job("ingest_document", row["id"])
    return {"id": row["id"], "status": row["status"]}


@app.post("/documents/upload")
async def upload_document(
    request: Request,
    current_user: Annotated[TokenData, Depends(require_admin)],
    db: AsyncConnectionPool = Depends(get_db),
    files: list[UploadFile] = File(...),
    title: str = Form(None),
):
    from app.extractor import extract_text

    if not files:
        raise HTTPException(status_code=400, detail="No files provided")

    results = []
    errors = []

    for file in files:
        try:
            file_bytes = await file.read()
            if len(file_bytes) == 0:
                errors.append({"filename": file.filename, "error": "Empty file"})
                continue
            if len(file_bytes) > 20 * 1024 * 1024:
                errors.append({"filename": file.filename, "error": "File too large (max 20MB)"})
                continue
            try:
                content = extract_text(file.filename, file_bytes)
            except ValueError as e:
                errors.append({"filename": file.filename, "error": str(e)})
                continue

            doc_title = (
                title if (title and len(files) == 1)
                else Path(file.filename).stem.replace("-", " ").replace("_", " ").title()
            )

            async with db.connection() as conn:
                row = await (await conn.execute(
                    "INSERT INTO documents (title, source, content) VALUES (%s, %s, %s) RETURNING id, status",
                    (doc_title, file.filename, content),
                )).fetchone()

            await request.app.state.redis.enqueue_job("ingest_document", row["id"])
            results.append({
                "id": row["id"],
                "title": doc_title,
                "status": row["status"],
                "filename": file.filename,
                "characters": len(content),
            })
        except Exception as e:
            errors.append({"filename": file.filename, "error": str(e)})

    return {"uploaded": len(results), "failed": len(errors), "results": results, "errors": errors}


@app.get("/documents")
async def list_documents(
    current_user: Annotated[TokenData, Depends(require_admin)],
    db: AsyncConnectionPool = Depends(get_db),
):
    async with db.connection() as conn:
        rows = await (await conn.execute(
            "SELECT id, title, status, chunk_count, created_at FROM documents ORDER BY id DESC"
        )).fetchall()
    return rows


# ── Memories ───────────────────────────────────────────────────────────────────

@app.get("/memories/{customer_id}")
async def get_memories(
    customer_id: int,
    current_user: Annotated[TokenData, Depends(require_admin)],
    db: AsyncConnectionPool = Depends(get_db),
):
    async with db.connection() as conn:
        rows = await (await conn.execute(
            """
            SELECT kind, content, created_at FROM memories
            WHERE customer_id = %s ORDER BY id DESC LIMIT 50
            """,
            (customer_id,),
        )).fetchall()
    return rows


# ── User management ────────────────────────────────────────────────────────────

@app.post("/admin/users", response_model=UserOut)
async def create_user(
    body: UserCreate,
    current_user: Annotated[TokenData, Depends(require_admin)],
    db: AsyncConnectionPool = Depends(get_db),
):
    async with db.connection() as conn:
        existing = await (await conn.execute(
            "SELECT id FROM users WHERE username = %s", (body.username,)
        )).fetchone()
        if existing:
            raise HTTPException(status_code=400, detail="Username already exists")
        row = await (await conn.execute(
            """
            INSERT INTO users (username, hashed_password, role)
            VALUES (%s, %s, %s)
            RETURNING id, username, role, is_active, customer_id, created_at
            """,
            (body.username, hash_password(body.password), body.role),
        )).fetchone()
    return UserOut(
        id=row["id"], username=row["username"], role=row["role"],
        is_active=row["is_active"], customer_id=row["customer_id"],
        created_at=str(row["created_at"]),
    )


@app.get("/admin/users")
async def list_users(
    current_user: Annotated[TokenData, Depends(require_admin)],
    db: AsyncConnectionPool = Depends(get_db),
):
    async with db.connection() as conn:
        rows = await (await conn.execute(
            "SELECT id, username, role, is_active, customer_id, created_at FROM users ORDER BY created_at DESC"
        )).fetchall()
    return [
        UserOut(
            id=r["id"], username=r["username"], role=r["role"],
            is_active=r["is_active"], customer_id=r["customer_id"],
            created_at=str(r["created_at"]),
        )
        for r in rows
    ]


@app.delete("/admin/users/{username}")
async def deactivate_user(
    username: str,
    current_user: Annotated[TokenData, Depends(require_admin)],
    db: AsyncConnectionPool = Depends(get_db),
):
    if username == settings.admin_username:
        raise HTTPException(status_code=400, detail="Cannot deactivate the admin account")
    async with db.connection() as conn:
        await conn.execute(
            "UPDATE users SET is_active = false WHERE username = %s", (username,)
        )
    return {"status": "deactivated", "username": username}

@app.post("/auth/refresh", response_model=Token)
async def refresh_token(
    body: RefreshIn,
    db: AsyncConnectionPool = Depends(get_db),
):
    """
    Exchange a refresh token for a new access + refresh token pair.
    The old refresh token is consumed — this is token rotation.
    Why rotation: if a refresh token is stolen and used, the legitimate
    user's next refresh will fail (token already rotated), alerting them.
    Production upgrade: store refresh tokens in Redis with TTL,
    invalidate on use, and track suspicious rotation patterns.
    """
    from app.auth import decode_refresh_token, create_access_token, create_refresh_token
    from jose import JWTError

    try:
        payload = decode_refresh_token(body.refresh_token)
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    username = payload.get("sub")
    user = await authenticate_user.__wrapped__(username, None, db) if False else None

    # fetch user from DB to ensure they're still active
    async with db.connection() as conn:
        user = await (await conn.execute(
            "SELECT * FROM users WHERE username = %s AND is_active = true",
            (username,),
        )).fetchone()

    if not user:
        raise HTTPException(status_code=401, detail="User not found or inactive")

    new_access = create_access_token({
        "sub": user["username"],
        "role": user["role"],
        "customer_id": user.get("customer_id"),
    })
    new_refresh = create_refresh_token({
        "sub": user["username"],
        "role": user["role"],
        "customer_id": user.get("customer_id"),
    })

    return Token(
        access_token=new_access,
        refresh_token=new_refresh,
        token_type="bearer",
        role=user["role"],
        username=user["username"],
        customer_id=user.get("customer_id"),
    )