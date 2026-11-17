import json
from datetime import datetime
from typing import Annotated, Optional
from pydantic import Field
from mcp_server.shared import error_payload, get_db_connection

OrderIdParam = Annotated[Optional[str], Field(description="Specific order ID (e.g., 'ORD-1001').")]
CustomerIdParam = Annotated[Optional[str], Field(description="Customer ID (e.g., 'CUST-101') to fetch all orders.")]
EmailParam = Annotated[Optional[str], Field(description="Registered customer email to fetch all orders.")]


def _format_order(row) -> dict:
    """Format database row into a structured order dictionary."""
    days_since_delivery = None
    within_30_day_window = False
    if row["delivered_at"]:
        delivered_dt = datetime.fromisoformat(row["delivered_at"])
        days_since_delivery = (datetime.utcnow() - delivered_dt).days
        within_30_day_window = days_since_delivery <= 30

    return {
        "order_id": row["order_id"],
        "customer_id": row["customer_id"],
        "item_name": row["item_name"],
        "category": row["category"],
        "amount_usd": row["amount_usd"],
        "order_status": row["status"],
        "days_since_delivery": days_since_delivery,
        "within_30_day_window": within_30_day_window,
    }


def lookup_order(
    order_id: OrderIdParam = None,
    customer_id: CustomerIdParam = None,
    email: EmailParam = None,
) -> str:
    """Fetch order item details, dollar amount, delivery timestamp, and return window eligibility."""
    if not any([order_id, customer_id, email]):
        return error_payload("MISSING_LOOKUP_IDENTIFIER", "Provide an order_id, customer_id, or email.")

    conn = get_db_connection()
    resolved_cust_id = customer_id.strip().upper() if customer_id else None

    if email:
        cust_row = conn.execute("SELECT customer_id FROM customers WHERE LOWER(email) = LOWER(?)", (email.strip(),)).fetchone()
        if not cust_row:
            conn.close()
            return error_payload("CUSTOMER_NOT_FOUND", f"No customer record matched email '{email}'.")
        if resolved_cust_id and resolved_cust_id != cust_row["customer_id"].upper():
            conn.close()
            return error_payload("CUSTOMER_IDENTIFIER_MISMATCH", "Provided customer_id and email do not belong to the same account.")
        resolved_cust_id = cust_row["customer_id"].upper()

    if order_id:
        row = conn.execute("SELECT * FROM orders WHERE UPPER(order_id) = UPPER(?)", (order_id.strip(),)).fetchone()
        conn.close()
        if not row:
            return error_payload("ORDER_NOT_FOUND", f"Order '{order_id}' does not exist.")
        if resolved_cust_id and row["customer_id"].upper() != resolved_cust_id:
            return error_payload("ORDER_OWNERSHIP_MISMATCH", f"Order '{order_id}' does not belong to customer '{resolved_cust_id}'.")
        return json.dumps({"status": "success", "orders": [_format_order(row)]})

    rows = conn.execute("SELECT * FROM orders WHERE UPPER(customer_id) = ?", (resolved_cust_id,)).fetchall()
    conn.close()
    if not rows:
        return error_payload("NO_ORDERS_FOUND", f"No orders found for customer '{resolved_cust_id}'.")
    return json.dumps({"status": "success", "orders": [_format_order(r) for r in rows]})
