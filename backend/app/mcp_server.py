"""
Our own MCP server — exposes orders and customers data as MCP tools + resources.

Why build your own MCP server:
- Most candidates only CONSUME existing MCP servers
- Building one proves you understand the protocol, not just the API call
- Standardised interface: the agent doesn't care what's behind the server
- Swap Postgres for any other backend → agent is unchanged

Three MCP primitives we implement:
- TOOLS     : functions the agent calls (get_order, get_customer, list_orders)
- RESOURCES : data the agent reads (order://ORD-123, customer://10)
- PROMPTS   : reusable prompt templates (support_context, refund_assessment)

Windows note: FastMCP is imported lazily to avoid the pywintypes
module-load issue on Windows. The pattern is identical to a normal
import — just deferred until first use.
"""
import asyncio
import json
import selectors
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.DefaultEventLoopPolicy())
    asyncio.set_event_loop(asyncio.SelectorEventLoop(selectors.SelectSelector()))

from app.db import init_db, get_pool


def _get_fastmcp():
    """Lazy import to avoid pywintypes Windows issue at module load time."""
    from mcp.server.fastmcp import FastMCP
    return FastMCP


# initialise FastMCP via lazy import
FastMCP = _get_fastmcp()

mcp = FastMCP(
    name="support-copilot-data",
    instructions=(
        "This server exposes customer support data: orders, customers, and refunds. "
        "Use get_order to look up a specific order. "
        "Use get_customer to look up a customer. "
        "Use list_customer_orders to see all orders for a customer. "
        "Use get_refund_status to check if an order has been refunded."
    ),
)


# ── TOOLS — functions the agent can call ──────────────────────────────────────

@mcp.tool()
async def get_order(order_id: str) -> str:
    """
    Get full details for a specific order by order ID.
    Returns order status, product, amount, and customer info.
    """
    pool = get_pool()
    async with pool.connection() as conn:
        row = await (await conn.execute(
            """
            SELECT o.order_id, o.product, o.amount, o.status, o.created_at,
                   c.name as customer_name, c.email as customer_email
            FROM orders o
            LEFT JOIN customers c ON o.customer_id = c.id
            WHERE o.order_id = %s
            """,
            (order_id,),
        )).fetchone()

    if not row:
        return json.dumps({"error": f"Order {order_id} not found"})

    return json.dumps({
        "order_id": row["order_id"],
        "product": row["product"],
        "amount": float(row["amount"]),
        "status": row["status"],
        "customer_name": row["customer_name"],
        "customer_email": row["customer_email"],
        "created_at": str(row["created_at"]),
    })


@mcp.tool()
async def get_customer(customer_id: int) -> str:
    """
    Get customer details including order count and total spend.
    """
    pool = get_pool()
    async with pool.connection() as conn:
        customer = await (await conn.execute(
            "SELECT id, name, email, external_id, created_at FROM customers WHERE id = %s",
            (customer_id,),
        )).fetchone()

        if not customer:
            return json.dumps({"error": f"Customer {customer_id} not found"})

        stats = await (await conn.execute(
            """
            SELECT COUNT(*) as order_count, COALESCE(SUM(amount), 0) as total_spend
            FROM orders WHERE customer_id = %s
            """,
            (customer_id,),
        )).fetchone()

    return json.dumps({
        "customer_id": customer["id"],
        "name": customer["name"],
        "email": customer["email"],
        "external_id": customer["external_id"],
        "order_count": stats["order_count"],
        "total_spend": float(stats["total_spend"]),
        "member_since": str(customer["created_at"]),
    })


@mcp.tool()
async def list_customer_orders(customer_id: int) -> str:
    """
    List all orders for a specific customer, most recent first.
    """
    pool = get_pool()
    async with pool.connection() as conn:
        rows = await (await conn.execute(
            """
            SELECT order_id, product, amount, status, created_at
            FROM orders
            WHERE customer_id = %s
            ORDER BY created_at DESC
            LIMIT 20
            """,
            (customer_id,),
        )).fetchall()

    orders = [
        {
            "order_id": r["order_id"],
            "product": r["product"],
            "amount": float(r["amount"]),
            "status": r["status"],
            "created_at": str(r["created_at"]),
        }
        for r in rows
    ]
    return json.dumps({"customer_id": customer_id, "orders": orders})


@mcp.tool()
async def get_refund_status(order_id: str) -> str:
    """
    Check if a refund has been issued for a specific order.
    Returns refund details if found, or not_found if no refund exists.
    """
    pool = get_pool()
    async with pool.connection() as conn:
        row = await (await conn.execute(
            "SELECT order_id, amount, reason, created_at FROM refunds WHERE order_id = %s",
            (order_id,),
        )).fetchone()

    if not row:
        return json.dumps({
            "order_id": order_id,
            "refund_status": "not_found",
            "message": "No refund found for this order.",
        })

    return json.dumps({
        "order_id": row["order_id"],
        "refund_status": "refunded",
        "amount": float(row["amount"]),
        "reason": row["reason"],
        "refunded_at": str(row["created_at"]),
    })


@mcp.tool()
async def search_orders_by_status(status: str) -> str:
    """
    Find all orders with a given status.
    Valid statuses: processing, shipped, delivered, cancelled.
    """
    allowed = {"processing", "shipped", "delivered", "cancelled"}
    if status not in allowed:
        return json.dumps({"error": f"Invalid status. Must be one of: {allowed}"})

    pool = get_pool()
    async with pool.connection() as conn:
        rows = await (await conn.execute(
            """
            SELECT o.order_id, o.product, o.amount, o.status,
                   c.name as customer_name
            FROM orders o
            LEFT JOIN customers c ON o.customer_id = c.id
            WHERE o.status = %s
            ORDER BY o.created_at DESC
            LIMIT 50
            """,
            (status,),
        )).fetchall()

    return json.dumps({
        "status": status,
        "count": len(rows),
        "orders": [
            {
                "order_id": r["order_id"],
                "product": r["product"],
                "amount": float(r["amount"]),
                "customer": r["customer_name"],
            }
            for r in rows
        ],
    })


# ── RESOURCES — data the agent can read ───────────────────────────────────────

@mcp.resource("order://{order_id}")
async def order_resource(order_id: str) -> str:
    """
    Read an order as a resource.
    URI: order://ORD-123
    Returns a human-readable summary of the order.
    """
    pool = get_pool()
    async with pool.connection() as conn:
        row = await (await conn.execute(
            "SELECT * FROM orders WHERE order_id = %s",
            (order_id,),
        )).fetchone()

    if not row:
        return f"Order {order_id} not found."

    return (
        f"Order: {row['order_id']}\n"
        f"Product: {row['product']}\n"
        f"Amount: ₹{row['amount']}\n"
        f"Status: {row['status']}\n"
        f"Created: {row['created_at']}"
    )


@mcp.resource("customer://{customer_id}")
async def customer_resource(customer_id: str) -> str:
    """
    Read a customer profile as a resource.
    URI: customer://10
    """
    pool = get_pool()
    async with pool.connection() as conn:
        row = await (await conn.execute(
            "SELECT * FROM customers WHERE id = %s",
            (customer_id,),
        )).fetchone()

    if not row:
        return f"Customer {customer_id} not found."

    return (
        f"Customer ID: {row['id']}\n"
        f"Name: {row['name'] or 'Unknown'}\n"
        f"Email: {row['email'] or 'Unknown'}\n"
        f"Member since: {row['created_at']}"
    )


# ── PROMPTS — reusable prompt templates ───────────────────────────────────────

@mcp.prompt()
def support_context(order_id: str, issue_type: str) -> str:
    """
    Generate a support context prompt for a given order and issue type.
    """
    return (
        f"You are handling a customer support case for order {order_id}.\n"
        f"Issue type: {issue_type}\n\n"
        f"Guidelines:\n"
        f"- Always verify the order exists before making promises\n"
        f"- For refunds: check the order status and refund policy\n"
        f"- For shipping issues: get the current status first\n"
        f"- Be empathetic but factual — never invent information\n"
        f"- If unsure, escalate to a human agent"
    )


@mcp.prompt()
def refund_assessment(order_id: str, reason: str) -> str:
    """
    Prompt template for assessing whether a refund should be approved.
    Used by operators reviewing refund requests in the approval queue.
    """
    return (
        f"Assess this refund request:\n"
        f"Order: {order_id}\n"
        f"Reason: {reason}\n\n"
        f"Check:\n"
        f"1. Is the order delivered?\n"
        f"2. Is it within the 30-day return window?\n"
        f"3. Is the reason valid (damaged, wrong item, not delivered)?\n"
        f"4. Has a refund already been issued for this order?\n\n"
        f"Recommend: APPROVE or REJECT with one sentence reason."
    )


# ── Startup ───────────────────────────────────────────────────────────────────

async def _startup():
    await init_db()
    print("[mcp] DB pool initialised")


if __name__ == "__main__":
    asyncio.run(_startup())
    print("[mcp] starting server on stdio transport")
    mcp.run(transport="stdio")