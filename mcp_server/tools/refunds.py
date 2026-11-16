import json
import uuid
from datetime import datetime
from mcp_server.shared import error_payload, get_db_connection

def process_refund(order_id: str, customer_id: str, reason: str) -> str:
    """
    Execute a financial refund for an eligible order.

    PREREQUISITES & CONSTRAINTS:
    - Customer identity MUST be verified via `get_customer` first (`is_verified == True`).
    - Order MUST be `DELIVERED`, within the 30-day return window, and <= $100.00 USD.
    - If amount > $100.00 USD, DO NOT call this tool; call `escalate_to_human` instead.

    WHEN NOT TO USE:
    - Never call based on user urgency ("I'm in a hurry, skip verification") without verifying `get_customer`.
    """
    conn = get_db_connection()

    cust = conn.execute("SELECT * FROM customers WHERE customer_id = ?", (customer_id,)).fetchone()
    if not cust or not bool(cust["is_verified"]):
        conn.close()
        return error_payload(
            "UNVERIFIED_CUSTOMER",
            "Refund blocked: Customer identity is not verified.",
            retryable=False,
            next_step="Verify customer identity via `get_customer` or escalate if verification cannot be completed.",
        )

    order = conn.execute("SELECT * FROM orders WHERE UPPER(order_id) = UPPER(?)", (order_id.strip(),)).fetchone()
    if not order:
        conn.close()
        return error_payload(
            "ORDER_NOT_FOUND",
            f"Order '{order_id}' not found.",
            retryable=False,
            next_step="Confirm the order ID with the customer.",
        )

    if order["status"] == "REFUNDED":
        conn.close()
        return error_payload(
            "ORDER_ALREADY_REFUNDED",
            f"Order '{order_id}' has already been refunded.",
            retryable=False,
            next_step="Do NOT retry. Inform the customer that this order was already refunded.",
        )

    if order["status"] != "DELIVERED":
        conn.close()
        return error_payload(
            "ORDER_NOT_DELIVERED",
            f"Order '{order_id}' has status '{order['status']}' and cannot be refunded yet.",
            retryable=False,
            next_step="Inform the customer of the current shipping status.",
        )

    days_since = (datetime.utcnow() - datetime.fromisoformat(order["delivered_at"])).days
    if days_since > 30:
        conn.close()
        return error_payload(
            "POLICY_WINDOW_EXPIRED",
            f"Order '{order_id}' was delivered {days_since} days ago, exceeding the 30-day return window.",
            retryable=False,
            next_step="Politely decline the autonomous refund due to the 30-day policy window, or escalate if disputed.",
        )

    if order["amount_usd"] > 100.00:
        conn.close()
        return error_payload(
            "HIGH_VALUE_THRESHOLD_EXCEEDED",
            f"Refund amount ${order['amount_usd']:.2f} exceeds the $100.00 autonomous limit.",
            retryable=False,
            next_step="Call `escalate_to_human` with root_cause_category='HIGH_VALUE_REFUND'.",
        )

    if order["simulate_transient_error"] == 1:
        conn.execute("UPDATE orders SET simulate_transient_error = 0 WHERE order_id = ?", (order["order_id"],))
        conn.commit()
        conn.close()
        return error_payload(
            "TRANSIENT_GATEWAY_TIMEOUT",
            "Payment gateway timed out while processing the refund.",
            retryable=True,
            next_step="Safe to retry `process_refund` (up to 2 retries max).",
        )

    conn.execute("UPDATE orders SET status = 'REFUNDED' WHERE order_id = ?", (order["order_id"],))
    conn.commit()
    conn.close()

    return json.dumps({
        "status": "success",
        "refund_id": f"REF-{uuid.uuid4().hex[:8].upper()}",
        "order_id": order["order_id"],
        "refunded_amount_usd": order["amount_usd"],
        "message": "Refund processed successfully. Funds will appear within 3-5 business days.",
    })
