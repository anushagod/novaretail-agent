import json
from typing import Annotated
from pydantic import Field
from datetime import datetime
from typing import Optional
from mcp_server.shared import error_payload, get_db_connection

OrderIdentifier = Annotated[
    str,
    Field(description="Unique order ID formatted as 'ORD-XXXX' (e.g., 'ORD-1001'). Do not pass customer IDs."),
]   

def lookup_order(order_id: OrderIdentifier) -> str:
    """
    Fetch order item details, dollar amount, delivery timestamp, and return window eligibility.

    WHEN TO USE:
    - Customer asks "Where is my order?" or requests a return/refund for a specific order ID (e.g., "ORD-1001").
    - Can be called in parallel across multiple order IDs for compound requests.

    WHEN NOT TO USE:
    - DO NOT use to look up customer profile/verification status (use `get_customer`).
    - DO NOT use to execute a refund (use `process_refund`).
    """
    conn = get_db_connection()
    row = conn.execute(
        "SELECT * FROM orders WHERE UPPER(order_id) = UPPER(?)",
        (order_id.strip(),),
    ).fetchone()
    conn.close()

    if not row:
        return error_payload(
            "ORDER_NOT_FOUND",
            f"Order '{order_id}' does not exist in NovaRetail records.",
            retryable=False,
            next_step="Ask the customer to double-check the order ID format (e.g., ORD-1001).",
        )

    days_since_delivery: Optional[int] = None
    within_30_day_window = False
    if row["delivered_at"]:
        delivered_dt = datetime.fromisoformat(row["delivered_at"])
        days_since_delivery = (datetime.utcnow() - delivered_dt).days
        within_30_day_window = days_since_delivery <= 30

    return json.dumps({
        "status": "success",
        "order_id": row["order_id"],
        "customer_id": row["customer_id"],
        "item_name": row["item_name"],
        "category": row["category"],
        "amount_usd": row["amount_usd"],
        "order_status": row["status"],
        "days_since_delivery": days_since_delivery,
        "within_30_day_window": within_30_day_window,
    })
