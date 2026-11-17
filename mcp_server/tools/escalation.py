import json
import uuid
from typing import Annotated
from pydantic import Field
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field
from mcp_server.shared import get_db_connection

class EscalationPayload(BaseModel):
    customer_id: str = Field(..., description="Customer ID (or 'UNKNOWN' if unauthenticated).")
    conversation_summary: str = Field(..., description="Concise summary of user intent and actions taken.")
    root_cause_category: Literal[
        "HIGH_VALUE_REFUND",
        "POLICY_EXCEPTION",
        "USER_REQUESTED",
        "SYSTEM_ERROR",
    ] = Field(..., description="Deterministic escalation category.")
    financial_exposure_usd: float = Field(..., description="Exact USD amount at issue, or 0.0 if non-financial.")
    recommended_next_action: str = Field(..., description="Concrete next step for the human agent.")

EscalationIdentifier = Annotated[
    EscalationPayload,
    Field(description="Structured escalation handoff payload containing customer ID, summary, category, financial exposure, and next action."),
]

def escalate_to_human(payload: EscalationIdentifier) -> str:
    """
    Create a structured escalation ticket for a human specialist and terminate the autonomous agent loop.

    WHEN TO USE:
    - Refund request exceeds $100.00 (`HIGH_VALUE_REFUND`).
    - Customer explicitly asks to speak to a human representative (`USER_REQUESTED`).
    - Request involves disputed fraud, chargebacks, or a policy gap (`POLICY_EXCEPTION`).
    - A tool fails repeatedly after 2 retries (`SYSTEM_ERROR`).

    WHEN NOT TO USE:
    - DO NOT escalate standard eligible refunds <= $100 within 30 days.
    """
    ticket_id = f"TKT-{uuid.uuid4().hex[:8].upper()}"
    conn = get_db_connection()
    conn.execute(
        """
        INSERT INTO escalations (
            ticket_id, customer_id, conversation_summary,
            root_cause_category, financial_exposure_usd,
            recommended_next_action, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            ticket_id,
            payload.customer_id,
            payload.conversation_summary,
            payload.root_cause_category,
            payload.financial_exposure_usd,
            payload.recommended_next_action,
            datetime.utcnow().isoformat(),
        ),
    )
    conn.commit()
    conn.close()

    return json.dumps({
        "status": "escalated",
        "ticket_id": ticket_id,
        "handoff_payload": payload.model_dump(),
        "instruction": "Escalation recorded. Inform the customer of their ticket ID and terminate the loop.",
    })
