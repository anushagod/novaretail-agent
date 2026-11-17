import json
import sqlite3
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
DB_PATH = Path(__file__).resolve().parent.parent / "db" / "novaretail.db"
POLICIES_DIR = Path(__file__).resolve().parent.parent / "policies"

VERIFIED_CUSTOMERS: set[str] = set()

def mark_customer_verified(customer_id: str) -> None:
    VERIFIED_CUSTOMERS.add(customer_id.strip().upper())

def is_customer_verified(customer_id: str) -> bool:
    return customer_id.strip().upper() in VERIFIED_CUSTOMERS

def reset_session_state() -> None:
    VERIFIED_CUSTOMERS.clear()

def get_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def error_payload(code: str, message: str, retryable: bool, next_step: str) -> str:
    return json.dumps({
        "status": "error",
        "error_code": code,
        "message": message,
        "retryable": retryable,
        "next_step": next_step,
    })
