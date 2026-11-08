import os
import sqlite3
from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional, Dict, Any
from pathlib import Path

DEFAULT_DB_PATH = Path(__file__).resolve().parent / "invoices.db"


def get_db_path() -> Path:
    env_path = os.getenv("PAYTRIAGE_DB_PATH")
    if env_path:
        return Path(env_path)
    return DEFAULT_DB_PATH


def get_db_connection(db_path: Optional[Path] = None) -> sqlite3.Connection:
    target_path = db_path or get_db_path()
    conn = sqlite3.connect(str(target_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db(db_path: Optional[Path] = None) -> None:
    """Initialize database tables for invoices and audit activity logs."""
    conn = get_db_connection(db_path)
    with conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS invoices (
                id TEXT PRIMARY KEY,
                invoice_number TEXT UNIQUE NOT NULL,
                customer_name TEXT NOT NULL,
                customer_email TEXT,
                total_amount TEXT NOT NULL,
                outstanding_amount TEXT NOT NULL,
                currency TEXT NOT NULL DEFAULT 'USD',
                status TEXT NOT NULL,
                due_date TEXT NOT NULL,
                reminder_count INTEGER NOT NULL DEFAULT 0,
                last_reminder_date TEXT,
                payment_history TEXT,
                has_promise_to_pay INTEGER NOT NULL DEFAULT 0,
                promise_due_date TEXT,
                notes TEXT,
                is_demo INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            );
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS activity_logs (
                id TEXT PRIMARY KEY,
                invoice_id TEXT NOT NULL,
                action_type TEXT NOT NULL,
                status TEXT NOT NULL,
                details TEXT,
                timestamp TEXT NOT NULL,
                FOREIGN KEY (invoice_id) REFERENCES invoices (id)
            );
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS reminder_drafts (
                id TEXT PRIMARY KEY,
                invoice_id TEXT NOT NULL,
                tone TEXT NOT NULL,
                subject TEXT NOT NULL,
                body TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'draft',
                source TEXT NOT NULL DEFAULT 'ai',
                fallback_reason TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (invoice_id) REFERENCES invoices (id)
            );
        """)
        # Safe column addition if table already existed
        try:
            conn.execute("ALTER TABLE reminder_drafts ADD COLUMN fallback_reason TEXT;")
        except sqlite3.OperationalError:
            pass
    conn.close()


def row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    d = dict(row)
    # Parse dates and booleans for recovery engine consumption
    if d.get("due_date"):
        d["due_date"] = date.fromisoformat(d["due_date"])
    if d.get("last_reminder_date"):
        d["last_reminder_date"] = date.fromisoformat(d["last_reminder_date"])
    else:
        d["last_reminder_date"] = None
    if d.get("promise_due_date"):
        d["promise_due_date"] = date.fromisoformat(d["promise_due_date"])
    else:
        d["promise_due_date"] = None

    d["total_amount"] = Decimal(d["total_amount"])
    d["outstanding_amount"] = Decimal(d["outstanding_amount"])
    d["has_promise_to_pay"] = bool(d["has_promise_to_pay"])
    d["is_demo"] = bool(d["is_demo"])
    return d


def get_all_invoices(db_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Retrieve all invoices from SQLite."""
    conn = get_db_connection(db_path)
    try:
        cur = conn.execute("SELECT * FROM invoices ORDER BY due_date ASC")
        rows = cur.fetchall()
        return [row_to_dict(r) for r in rows]
    finally:
        conn.close()


def get_invoice_by_id(invoice_id: str, db_path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """Retrieve a single invoice by ID or invoice_number from SQLite."""
    conn = get_db_connection(db_path)
    try:
        cur = conn.execute("SELECT * FROM invoices WHERE id = ? OR invoice_number = ?", (invoice_id, invoice_id))
        row = cur.fetchone()
        if row:
            return row_to_dict(row)
        return None
    finally:
        conn.close()


def insert_invoice(inv: Dict[str, Any], db_path: Optional[Path] = None) -> None:
    """Insert or replace an invoice record."""
    conn = get_db_connection(db_path)
    try:
        with conn:
            conn.execute("""
                INSERT OR REPLACE INTO invoices (
                    id, invoice_number, customer_name, customer_email,
                    total_amount, outstanding_amount, currency, status,
                    due_date, reminder_count, last_reminder_date,
                    payment_history, has_promise_to_pay, promise_due_date,
                    notes, is_demo, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                inv["id"],
                inv.get("invoice_number", inv["id"]),
                inv.get("customer_name", "Customer"),
                inv.get("customer_email"),
                str(inv["total_amount"]),
                str(inv["outstanding_amount"]),
                inv.get("currency", "USD"),
                inv["status"],
                inv["due_date"].isoformat() if isinstance(inv["due_date"], (date, datetime)) else str(inv["due_date"]),
                int(inv.get("reminder_count", 0)),
                inv["last_reminder_date"].isoformat() if isinstance(inv.get("last_reminder_date"), (date, datetime)) else inv.get("last_reminder_date"),
                inv.get("payment_history"),
                1 if inv.get("has_promise_to_pay") else 0,
                inv["promise_due_date"].isoformat() if isinstance(inv.get("promise_due_date"), (date, datetime)) else inv.get("promise_due_date"),
                inv.get("notes"),
                1 if inv.get("is_demo", True) else 0,
                inv.get("created_at", datetime.now().isoformat())
            ))
    finally:
        conn.close()


def clear_invoices(db_path: Optional[Path] = None) -> None:
    """Clear all records from database (used for testing and seeding)."""
    conn = get_db_connection(db_path)
    try:
        with conn:
            conn.execute("DELETE FROM reminder_drafts;")
            conn.execute("DELETE FROM activity_logs;")
            conn.execute("DELETE FROM invoices;")
    finally:
        conn.close()


def save_reminder_draft(draft: Dict[str, Any], db_path: Optional[Path] = None) -> None:
    """Insert or replace a reminder draft record."""
    conn = get_db_connection(db_path)
    try:
        with conn:
            conn.execute("""
                INSERT OR REPLACE INTO reminder_drafts (
                    id, invoice_id, tone, subject, body, status, source, fallback_reason, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                draft["id"],
                draft["invoice_id"],
                draft["tone"],
                draft["subject"],
                draft["body"],
                draft.get("status", "draft"),
                draft.get("source", "ai"),
                draft.get("fallback_reason"),
                draft.get("created_at", datetime.now().isoformat()),
                draft.get("updated_at", datetime.now().isoformat()),
            ))
    finally:
        conn.close()


def get_reminder_draft(draft_id: str, db_path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """Retrieve a single reminder draft by ID."""
    conn = get_db_connection(db_path)
    try:
        cur = conn.execute("SELECT * FROM reminder_drafts WHERE id = ?", (draft_id,))
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def update_reminder_draft(draft_id: str, updates: Dict[str, Any], db_path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """Update fields of an existing reminder draft."""
    conn = get_db_connection(db_path)
    try:
        fields = []
        values = []
        for k, v in updates.items():
            fields.append(f"{k} = ?")
            values.append(v)
        fields.append("updated_at = ?")
        values.append(datetime.now().isoformat())
        values.append(draft_id)

        with conn:
            conn.execute(f"UPDATE reminder_drafts SET {', '.join(fields)} WHERE id = ?", values)
        return get_reminder_draft(draft_id, db_path=db_path)
    finally:
        conn.close()


def list_reminder_drafts(invoice_id: Optional[str] = None, db_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """List reminder drafts, optionally filtered by invoice_id."""
    conn = get_db_connection(db_path)
    try:
        if invoice_id:
            cur = conn.execute("SELECT * FROM reminder_drafts WHERE invoice_id = ? ORDER BY created_at DESC", (invoice_id,))
        else:
            cur = conn.execute("SELECT * FROM reminder_drafts ORDER BY created_at DESC")
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def log_activity(
    invoice_id: str,
    action_type: str,
    status: str,
    details: Optional[str] = None,
    log_id: Optional[str] = None,
    db_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Record an audit trail activity log entry."""
    import uuid
    conn = get_db_connection(db_path)
    entry_id = log_id or f"ACT-{uuid.uuid4().hex[:8].upper()}"
    ts = datetime.now().isoformat()
    try:
        with conn:
            conn.execute("""
                INSERT INTO activity_logs (id, invoice_id, action_type, status, details, timestamp)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (entry_id, invoice_id, action_type, status, details, ts))
        return {
            "id": entry_id,
            "invoice_id": invoice_id,
            "action_type": action_type,
            "status": status,
            "details": details,
            "timestamp": ts,
        }
    finally:
        conn.close()


def get_activity_logs(invoice_id: Optional[str] = None, db_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Retrieve activity logs, optionally filtered by invoice_id."""
    conn = get_db_connection(db_path)
    try:
        if invoice_id:
            cur = conn.execute("SELECT * FROM activity_logs WHERE invoice_id = ? ORDER BY timestamp DESC", (invoice_id,))
        else:
            cur = conn.execute("SELECT * FROM activity_logs ORDER BY timestamp DESC")
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()

