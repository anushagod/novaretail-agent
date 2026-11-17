import json
from typing import Annotated
from pydantic import Field
from mcp_server.shared import error_payload, get_db_connection, mark_customer_verified

CustomerIdentifier = Annotated[
    str,
    Field(description=("Customer ID (e.g., 'CUST-101') or registered email address "
                       "(e.g., 'alice@example.com'). Do not pass order IDs.")),
]

def get_customer(identifier: CustomerIdentifier) -> str:
    """
    Retrieve a customer's profile, account standing, and identity verification status.

    WHEN TO USE:
    - You need to verify a customer's identity before processing a refund or inspecting sensitive account details.
    - Input can be either a customer ID (e.g., "CUST-101") or email address (e.g., "alice@example.com").

    WHEN NOT TO USE:
    - DO NOT call for general policy questions where no customer identifier was provided.
    - DO NOT use to fetch order line items or delivery dates (use `lookup_order` instead).
    """
    conn = get_db_connection()
    row = conn.execute(
        "SELECT * FROM customers WHERE customer_id = ? OR LOWER(email) = LOWER(?)",
        (identifier.strip(), identifier.strip()),
    ).fetchone()
    conn.close()

    if not row:
        return error_payload(
            "CUSTOMER_NOT_FOUND",
            f"No customer record matched identifier '{identifier}'.",
            retryable=False,
            next_step="Ask the customer to confirm their registered email address or customer ID.",
        )

    mark_customer_verified(row["customer_id"])

    return json.dumps({
        "status": "success",
        "customer_id": row["customer_id"],
        "full_name": row["full_name"],
        "email": row["email"],
        "is_verified": True,
    })
