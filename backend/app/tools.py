"""
Agent tools — actions the agent can take with real side effects.

Design principles:
1. IDEMPOTENT: calling a tool twice has the same result as once.
   Critical because the approval flow can retry on network failure.
2. APPROVAL FLAG: each tool declares whether it needs human approval.
   Read-only or harmless tools skip the approval queue entirely.
3. TOOL REGISTRY: maps action name → function + metadata.
   The graph looks up tools here — adding a new tool is one entry.
4. NO AUTO-EXECUTION: consequential tools only run after human approval.

Industry pattern: read broadly, act narrowly.
The agent can read everything but can only act through these tools,
and only consequential ones need a human in the loop.
"""
import json
from app.db import get_pool


# ── Order & Fulfillment ───────────────────────────────────────────────────────

async def issue_refund(order_id: str, amount: float, reason: str, **kwargs) -> dict:
    """
    Issue a refund for an order.

    Idempotency: checks for existing refund before inserting.
    Real world: would call Stripe/Razorpay refund API.
    """
    pool = get_pool()
    async with pool.connection() as conn:
        existing = await (await conn.execute(
            "SELECT id FROM refunds WHERE order_id = %s",
            (order_id,),
        )).fetchone()

        if existing:
            return {
                "status": "already_refunded",
                "order_id": order_id,
                "message": f"Order {order_id} was already refunded. No duplicate issued.",
            }

        await conn.execute(
            "INSERT INTO refunds (order_id, amount, reason) VALUES (%s, %s, %s)",
            (order_id, amount, reason),
        )

    return {
        "status": "refunded",
        "order_id": order_id,
        "amount": amount,
        "message": f"Refund of ₹{amount} issued for order {order_id}. Customer will receive it in 5-7 business days.",
    }


async def cancel_order(order_id: str, reason: str, **kwargs) -> dict:
    """
    Cancel an order before shipment.

    Idempotency: safe to call twice — second call returns already_cancelled.
    Real world: would call order management system API.
    """
    pool = get_pool()
    async with pool.connection() as conn:
        existing = await (await conn.execute(
            "SELECT status FROM tickets WHERE subject = %s",
            (f"CANCELLED:{order_id}",),
        )).fetchone()

        if existing:
            return {
                "status": "already_cancelled",
                "order_id": order_id,
                "message": f"Order {order_id} was already cancelled.",
            }

        await conn.execute(
            """
            INSERT INTO tickets (subject, body, status, urgency)
            VALUES (%s, %s, 'open', 'high')
            """,
            (f"CANCELLED:{order_id}", f"Order cancelled. Reason: {reason}"),
        )

    return {
        "status": "cancelled",
        "order_id": order_id,
        "message": f"Order {order_id} has been cancelled. Refund will be processed automatically.",
    }


async def update_order_status(order_id: str, new_status: str, **kwargs) -> dict:
    """
    Update an order's lifecycle status.

    Allowed statuses are strictly validated — the agent cannot set
    arbitrary statuses, only the defined lifecycle states.
    """
    allowed = {"processing", "shipped", "delivered", "cancelled"}
    if new_status not in allowed:
        return {
            "status": "error",
            "message": f"Invalid status '{new_status}'. Allowed: {allowed}",
        }

    # Real world: call order management API here
    return {
        "status": "updated",
        "order_id": order_id,
        "new_status": new_status,
        "message": f"Order {order_id} status updated to '{new_status}'.",
    }


async def track_shipment(order_id: str, **kwargs) -> dict:
    """
    Fetch live tracking status for an order.

    READ-ONLY — no approval needed.
    Real world: call courier API (Shiprocket, FedEx, DHL).
    We simulate a response here.
    """
    # Simulated response — replace with real courier API call
    return {
        "status": "in_transit",
        "order_id": order_id,
        "location": "Mumbai sorting facility",
        "estimated_delivery": "2026-06-30",
        "message": f"Order {order_id} is in transit. Expected delivery: June 30.",
    }


# ── Customer Account ──────────────────────────────────────────────────────────

async def apply_store_credit(customer_id: int, amount: float, reason: str, **kwargs) -> dict:
    """
    Add store credit to a customer's account as an alternative to cash refund.

    Idempotency: not strictly idempotent (credits can stack intentionally),
    but amount + reason together identify a unique credit for audit purposes.
    Real world: update wallet balance in your payments system.
    """
    if not customer_id:
        return {"status": "error", "message": "customer_id is required"}

    pool = get_pool()
    async with pool.connection() as conn:
        await conn.execute(
            "INSERT INTO store_credits (customer_id, amount, reason) VALUES (%s, %s, %s)",
            (customer_id, amount, reason),
        )

    return {
        "status": "credit_applied",
        "customer_id": customer_id,
        "amount": amount,
        "message": f"₹{amount} store credit added to your account. Use it on your next order.",
    }


# ── Communication ─────────────────────────────────────────────────────────────

async def send_email(customer_id: int, subject: str, body: str, **kwargs) -> dict:
    """
    Send a follow-up email to the customer.

    Needs approval: external communication goes out under the company's name.
    Real world: call SendGrid/AWS SES API.
    We log to emails_sent table to show the pattern.
    """
    if not customer_id:
        return {"status": "error", "message": "customer_id is required"}

    pool = get_pool()
    async with pool.connection() as conn:
        await conn.execute(
            "INSERT INTO emails_sent (customer_id, subject, body) VALUES (%s, %s, %s)",
            (customer_id, subject, body),
        )

    return {
        "status": "sent",
        "customer_id": customer_id,
        "subject": subject,
        "message": f"Email '{subject}' sent to customer.",
    }


# ── Internal / Ops ────────────────────────────────────────────────────────────

async def escalate_ticket(customer_id: int, reason: str, message: str, **kwargs) -> dict:
    """
    Create an escalation ticket for a human agent.

    Real world: call Zendesk/Freshdesk ticket creation API.
    """
    pool = get_pool()
    async with pool.connection() as conn:
        row = await (await conn.execute(
            """
            INSERT INTO tickets (customer_id, subject, body, status, urgency)
            VALUES (%s, %s, %s, 'open', 'high')
            RETURNING id
            """,
            (customer_id or None, reason[:200], message[:1000]),
        )).fetchone()

    return {
        "status": "escalated",
        "ticket_id": row["id"],
        "message": f"Ticket #{row['id']} created. A human agent will follow up within 2 hours.",
    }


async def add_internal_note(customer_id: int, note: str, ticket_id: int = None, **kwargs) -> dict:
    """
    Add an internal note visible only to support agents, not the customer.

    READ-ONLY risk level — no approval needed.
    Used by the agent to annotate what it found/did for the next human reviewer.
    """
    if not customer_id:
        return {"status": "error", "message": "customer_id is required"}

    pool = get_pool()
    async with pool.connection() as conn:
        await conn.execute(
            """
            INSERT INTO internal_notes (customer_id, ticket_id, note)
            VALUES (%s, %s, %s)
            """,
            (customer_id, ticket_id or None, note),
        )

    return {
        "status": "note_added",
        "message": "Internal note added for agent review.",
    }


# ── Tool Registry ─────────────────────────────────────────────────────────────
#
# needs_approval=True  → graph pauses, operator must approve before execution
# needs_approval=False → executes immediately, no interruption
#
# This is the single place you add a new tool.
# The graph, the approval endpoint, and the action planner all read from here.

TOOL_REGISTRY = {
    "issue_refund": {
        "fn": issue_refund,
        "needs_approval": True,
        "description": "Issue a cash refund for an order. Needs: order_id, amount, reason.",
    },
    "cancel_order": {
        "fn": cancel_order,
        "needs_approval": True,
        "description": "Cancel an order before shipment. Needs: order_id, reason.",
    },
    "update_order_status": {
        "fn": update_order_status,
        "needs_approval": True,
        "description": "Update order lifecycle status. Needs: order_id, new_status (processing/shipped/delivered/cancelled).",
    },
    "apply_store_credit": {
        "fn": apply_store_credit,
        "needs_approval": True,
        "description": "Add store credit to customer account. Needs: customer_id, amount, reason.",
    },
    "send_email": {
        "fn": send_email,
        "needs_approval": True,
        "description": "Send follow-up email to customer. Needs: customer_id, subject, body.",
    },
    "escalate_ticket": {
        "fn": escalate_ticket,
        "needs_approval": True,
        "description": "Create escalation ticket for human agent. Needs: customer_id, reason, message.",
    },
    "track_shipment": {
        "fn": track_shipment,
        "needs_approval": False,   # read-only, no approval needed
        "description": "Fetch live tracking status. Needs: order_id.",
    },
    "add_internal_note": {
        "fn": add_internal_note,
        "needs_approval": False,   # internal only, harmless
        "description": "Add internal note for agents. Needs: customer_id, note.",
    },
}