"""
MCP client — calls our MCP server tools from inside the agent.

Why go through MCP instead of calling the DB directly:
- Agent is decoupled from the data layer
- Swap Postgres for any backend → agent unchanged
- Standard protocol: same client code works with ANY MCP server
- The MCP server can be hosted separately, versioned independently

All imports are lazy (inside functions) to avoid the Windows
pywintypes module-load issue when uvicorn imports the app.
"""
import json


async def fetch_order_context(order_id: str) -> dict:
    """
    Fetch full order context via MCP get_order tool.
    Returns parsed dict or error dict.
    """
    from app.mcp_server import get_order
    result = await get_order(order_id)
    return json.loads(result)


async def fetch_customer_context(customer_id: int) -> dict:
    """
    Fetch customer profile + order history via MCP tools.
    Combines get_customer and list_customer_orders into one call.
    """
    from app.mcp_server import get_customer, list_customer_orders
    customer = json.loads(await get_customer(customer_id))
    orders = json.loads(await list_customer_orders(customer_id))
    return {**customer, "recent_orders": orders.get("orders", [])}


async def check_refund_status(order_id: str) -> dict:
    """
    Check refund status for an order via MCP get_refund_status tool.
    """
    from app.mcp_server import get_refund_status
    result = await get_refund_status(order_id)
    return json.loads(result)