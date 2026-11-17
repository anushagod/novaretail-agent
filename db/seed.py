import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

DB_PATH = Path(__file__).parent / "novaretail.db"

def seed_database():
    if DB_PATH.exists():
        DB_PATH.unlink()

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Create Customers Table
    cursor.execute("""
        CREATE TABLE customers (
            customer_id TEXT PRIMARY KEY,
            full_name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL
        )
    """)

    # Create Orders Table
    cursor.execute("""
        CREATE TABLE orders (
            order_id TEXT PRIMARY KEY,
            customer_id TEXT NOT NULL,
            item_name TEXT NOT NULL,
            category TEXT NOT NULL,
            amount_usd REAL NOT NULL,
            status TEXT NOT NULL,
            delivered_at TEXT,
            simulate_transient_error INTEGER DEFAULT 0,
            FOREIGN KEY (customer_id) REFERENCES customers (customer_id)
        )
    """)

    # Create Escalation Tickets Table
    cursor.execute("""
        CREATE TABLE escalations (
            ticket_id TEXT PRIMARY KEY,
            customer_id TEXT NOT NULL,
            conversation_summary TEXT NOT NULL,
            root_cause_category TEXT NOT NULL,
            financial_exposure_usd REAL NOT NULL,
            recommended_next_action TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    now = datetime.utcnow()

    # Seed Customers
    customers = [
        ("CUST-101", "Alice Vance", "alice@example.com"),
        ("CUST-102", "Bob Mercer", "bob@example.com"),
        ("CUST-103", "Clara Oswald", "clara@example.com"),
    ]
    cursor.executemany("INSERT INTO customers VALUES (?, ?, ?)", customers)

    # Seed Orders (covering Happy Path, High Value, Expired, Already Refunded, Transient Timeout, Multi-Concern)
    orders = [
        # Scenario 1: Happy Path ($45, delivered 10 days ago, verified customer)
        ("ORD-1001", "CUST-101", "Ceramic Coffee Mug", "home", 45.00, "DELIVERED", (now - timedelta(days=10)).isoformat(), 0),
        # Scenario 2: Gate Bypass Attempt ($60, unverified customer CUST-102)
        ("ORD-1002", "CUST-102", "Wireless Mouse", "electronics", 60.00, "DELIVERED", (now - timedelta(days=5)).isoformat(), 0),
        # Scenario 3: High-Value Escalation ($240, delivered 7 days ago, verified customer)
        ("ORD-1003", "CUST-101", "Noise-Cancelling Headphones", "electronics", 240.00, "DELIVERED", (now - timedelta(days=7)).isoformat(), 0),
        # Scenario 4a: Transient Gateway Timeout on first try, then succeeds ($35)
        ("ORD-1004", "CUST-103", "Insulated Water Bottle", "home", 35.00, "DELIVERED", (now - timedelta(days=4)).isoformat(), 1),
        # Scenario 4b: Permanent Error - Already Refunded ($50)
        ("ORD-1005", "CUST-103", "Canvas Tote Bag", "apparel", 50.00, "REFUNDED", (now - timedelta(days=12)).isoformat(), 0),
        # Scenario 5: Multi-Concern Order (In Transit jacket + Expired 45-day item)
        ("ORD-1006", "CUST-101", "Winter Parka", "apparel", 120.00, "IN_TRANSIT", None, 0),
        ("ORD-1007", "CUST-101", "Desk Lamp", "home", 40.00, "DELIVERED", (now - timedelta(days=45)).isoformat(), 0),
    ]
    cursor.executemany("INSERT INTO orders VALUES (?, ?, ?, ?, ?, ?, ?, ?)", orders)

    conn.commit()
    conn.close()
    print(f"Database seeded successfully at {DB_PATH}")


if __name__ == "__main__":
    seed_database()
