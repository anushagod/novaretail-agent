import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

@dataclass
class SessionGuardrails:
    """
    Orchestrator-level programmatic gates and structured observability.
    Intercepts tool calls before and after MCP execution.
    """

    session_id: str
    max_retries_per_tool: int = 2
    verified_customer_ids: set[str] = field(default_factory=set)
    retryable_failure_counts: dict[str, int] = field(default_factory=dict)
    trace_logs: list[dict[str, Any]] = field(default_factory=list)
    total_input_tokens: int = 0
    total_output_tokens: int = 0

    def record_token_usage(self, input_tokens: int, output_tokens: int) -> None:
        """Track cumulative token usage per conversation session."""
        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens

    def validate_user_input(self, user_text: str, max_chars: int = 2000) -> str | None:
        """
        Lightweight, zero-token input guardrail run BEFORE calling the Claude API.
        Returns a polite refusal string if blocked, or None if valid to send to Claude.
        """
        cleaned = user_text.strip()
        if not cleaned:
            self._log_event("INPUT_BLOCK", "user_input", {"length": 0}, {"reason": "EMPTY_INPUT"}, 0.0)
            return "It looks like your message was empty. How can I help you with your NovaRetail order or account today?"

        if len(cleaned) > max_chars:
            self._log_event("INPUT_BLOCK", "user_input", {"length": len(cleaned)}, {"reason": "INPUT_TOO_LONG"}, 0.0)
            return (
                f"Your message is too long ({len(cleaned)} characters). "
                f"Please summarize your NovaRetail support request in under {max_chars} characters."
            )

        return None

    def pre_tool_check(self, tool_name: str, tool_input: dict[str, Any]) -> str | None:
        """
        Pre-execution hook run BEFORE forwarding a tool call to the MCP server.
        Returns a JSON error string (matching shared.error_payload) to block execution,
        or None if the call is permitted.
        """
        retry_key = self._make_retry_key(tool_name, tool_input)

        # Gate 2: Circuit Breaker (halt after 2 failed retries without progress)
        if self.retryable_failure_counts.get(retry_key, 0) > self.max_retries_per_tool:
            error_json = self._format_error(
                code="CIRCUIT_BREAKER_TRIGGERED",
                message=(
                    f"Tool '{tool_name}' exceeded {self.max_retries_per_tool} retries without success."
                ),
                retryable=False,
                next_step="Stop retrying immediately and call `escalate_to_human` with root_cause_category='SYSTEM_ERROR'.",
            )
            self._log_event("GUARDRAIL_BLOCK", tool_name, tool_input, json.loads(error_json), 0.0)
            return error_json

        # Gate 1: Programmatic Prerequisite Gate for process_refund
        if tool_name == "process_refund":
            raw_cid = str(tool_input.get("customer_id", "")).strip().upper()
            if not raw_cid or raw_cid not in self.verified_customer_ids:
                error_json = self._format_error(
                    code="UNVERIFIED_CUSTOMER",
                    message=(
                        "Blocked by orchestrator pre-execution gate: Customer identity has not been "
                        "verified via `get_customer` in this active session."
                    ),
                    retryable=False,
                    next_step="Call `get_customer` with the customer's ID or registered email before attempting a refund.",
                )
                self._log_event("GUARDRAIL_BLOCK", tool_name, tool_input, json.loads(error_json), 0.0)
                return error_json

        return None

    def post_tool_record(
        self,
        tool_name: str,
        tool_input: dict[str, Any],
        raw_output: str,
        latency_ms: float,
    ) -> dict[str, Any]:
        """
        Post-execution hook run AFTER receiving a response from the MCP server.
        Syncs verified session state, updates retry counters, and logs JSON traces.
        """
        parsed = self._safe_parse(raw_output)
        retry_key = self._make_retry_key(tool_name, tool_input)
        status = str(parsed.get("status", "")).lower()

        # Sync verified customer state only when get_customer succeeds
        if tool_name == "get_customer" and status == "success":
            cid = str(parsed.get("customer_id", "")).strip().upper()
            if cid:
                self.verified_customer_ids.add(cid)

        # Update retry counter for Circuit Breaker
        if status == "error":
            if parsed.get("retryable") is True:
                self.retryable_failure_counts[retry_key] = (
                    self.retryable_failure_counts.get(retry_key, 0) + 1
                )
            else:
                # Non-retryable error: immediately trip circuit breaker if model tries to loop on it
                self.retryable_failure_counts[retry_key] = self.max_retries_per_tool + 1
        else:
            # Clear failure counter on success
            self.retryable_failure_counts.pop(retry_key, None)

        self._log_event("TOOL_EXECUTION", tool_name, tool_input, parsed, latency_ms)
        return parsed

    def _make_retry_key(self, tool_name: str, tool_input: dict[str, Any]) -> str:
        # Handle nested payload dict in escalate_to_human
        if "payload" in tool_input and isinstance(tool_input["payload"], dict):
            target = tool_input["payload"].get("customer_id", "escalation")
        else:
            target = (
                tool_input.get("order_id")
                or tool_input.get("customer_id")
                or tool_input.get("identifier")
                or tool_input.get("email")
                or "global"
            )
        return f"{tool_name}:{str(target).strip().upper()}"

    def _format_error(self, code: str, message: str, retryable: bool, next_step: str) -> str:
        return json.dumps(
            {
                "status": "error",
                "error_code": code,
                "message": message,
                "retryable": retryable,
                "next_step": next_step,
            }
        )

    def _safe_parse(self, raw_output: str) -> dict[str, Any]:
        if isinstance(raw_output, dict):
            return raw_output
        try:
            return json.loads(raw_output)
        except (json.JSONDecodeError, TypeError):
            return {"raw_output": str(raw_output)}

    def _log_event(
        self,
        event_type: str,
        tool_name: str,
        tool_input: dict[str, Any],
        output: dict[str, Any],
        latency_ms: float,
    ) -> None:
        self.trace_logs.append(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "session_id": self.session_id,
                "event_type": event_type,
                "tool_name": tool_name,
                "input": tool_input,
                "output": output,
                "latency_ms": round(latency_ms, 2),
                "verified_customers": sorted(self.verified_customer_ids),
            }
        )

    def get_summary_metrics(self) -> dict[str, Any]:
        """Return observability summary for eval_results.json."""
        return {
            "session_id": self.session_id,
            "verified_customers": sorted(self.verified_customer_ids),
            "total_tool_events": len(self.trace_logs),
            "guardrail_blocks": sum(1 for e in self.trace_logs if e["event_type"] == "GUARDRAIL_BLOCK"),
            "token_usage": {
                "input_tokens": self.total_input_tokens,
                "output_tokens": self.total_output_tokens,
            },
            "trace": self.trace_logs,
        }

    def export_traces(self, output_path: str | Path) -> None:
        Path(output_path).write_text(json.dumps(self.get_summary_metrics(), indent=2), encoding="utf-8")
