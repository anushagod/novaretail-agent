import json
from typing import Annotated
from pydantic import Field
from mcp_server.shared import POLICIES_DIR, error_payload

queryIdentifier = Annotated[
    str,
    Field(description="Keywords describing the policy topic (e.g., 'electronics return window', 'refund timeline'). Never include customer PII."),
]

def search_policy(query: queryIdentifier) -> str:
    """
    Search NovaRetail's official policy documents (returns, electronics windows, shipping, verification rules).

    WHEN TO USE:
    - Customer asks general policy questions (e.g., "What is your return window for electronics?").
    - You need to verify general company rules before taking action.

    WHEN NOT TO USE:
    - DO NOT use to look up customer-specific accounts or order statuses.
    - DO NOT ask the customer for their email or ID before calling this tool.

    INPUT:
    - query: Keywords describing the policy topic (e.g., "electronics return window", "refund timeline").
    """
    if not POLICIES_DIR.exists():
        return error_payload(
            "POLICY_STORE_UNAVAILABLE",
            "Policy directory is missing.",
            retryable=False,
            next_step="Escalate to human with SYSTEM_ERROR.",
        )

    keywords = [w.lower() for w in query.split() if len(w) > 2]
    matches = []

    for md_file in POLICIES_DIR.glob("*.md"):
        content = md_file.read_text(encoding="utf-8")
        for line in content.splitlines():
            if any(kw in line.lower() for kw in keywords):
                matches.append(f"[{md_file.name}] {line.strip()}")

    if not matches:
        all_docs = {f.name: f.read_text(encoding="utf-8") for f in POLICIES_DIR.glob("*.md")}
        return json.dumps({"status": "success", "results": all_docs})

    return json.dumps({"status": "success", "matched_rules": matches})
