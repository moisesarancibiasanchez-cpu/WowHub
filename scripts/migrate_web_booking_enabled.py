#!/usr/bin/env python3
"""
Migration: Add web_booking_enabled column to site_configs table.

Run: python scripts/migrate_web_booking_enabled.py

Supports both SQLite (dev) and PostgreSQL (prod).
Idempotent — safe to run multiple times.

Usage:
  python scripts/migrate_web_booking_enabled.py

Environment variables (optional overrides):
  DATABASE_URL — full SQLAlchemy URL (e.g. postgresql://user:pass@host/db)
  DATABASE_URL takes precedence over DB_PATH (SQLite fallback).
"""
from __future__ import annotations

import logging
import os
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# ── Bootstrap ────────────────────────────────────────────────────────────────
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)

if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

DB_PATH = os.path.join(_ROOT, "wowhub.db")
DATABASE_URL = os.environ.get("DATABASE_URL", "")


def _dialect(conn) -> str:
    """Return 'postgresql' or 'sqlite' based on the connection."""
    dialect = getattr(conn, "dialect", None)
    if dialect is not None:
        return dialect.name
    # Fallback for sqlite3.Connection objects
    try:
        import sqlite3
        if isinstance(conn, sqlite3.Connection):
            return "sqlite"
    except Exception:
        pass
    engine = getattr(conn, "engine", None)
    if engine is not None:
        return getattr(engine, "dialect", None).name
    return ""


def _pg_column_exists(conn, table: str, column: str) -> bool:
    from sqlalchemy import text

    row = conn.execute(
        text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_schema = current_schema() "
            "AND table_name = :t AND column_name = :c"
        ),
        {"t": table, "c": column},
    ).first()
    return row is not None


def _sqlite_column_exists(conn, table: str, column: str) -> bool:
    import sqlite3

    cursor = conn.execute(f"PRAGMA table_info({table})")
    rows = cursor.fetchall()
    return any(row[1] == column for row in rows)


def migrate() -> int:
    """Add web_booking_enabled column if it doesn't exist.
    Returns the number of columns added (0 = already exists, 1 = added).
    """
    import sqlite3

    col_name = "web_booking_enabled"
    table = "site_configs"

    # ── Step 1: detect DB type ────────────────────────────────────────────────
    if DATABASE_URL:
        # Use SQLAlchemy engine (supports both SQLite and PostgreSQL)
        try:
            from sqlalchemy import create_engine, text
            from sqlalchemy.engine import Connection

            engine = create_engine(DATABASE_URL)
            with engine.connect() as conn:
                dialect = _dialect(conn)

                if dialect == "postgresql":
                    if _pg_column_exists(conn, table, col_name):
                        logger.info(
                            "Column %s.%s already exists — no-op.",
                            table, col_name,
                        )
                        return 0

                    conn.execute(
                        text(
                            f"ALTER TABLE {table} "
                            f"ADD COLUMN {col_name} BOOLEAN NOT NULL DEFAULT true"
                        )
                    )
                    conn.commit()
                    logger.info(
                        "✅ Added '%s' column to %s (PostgreSQL, default: True).",
                        col_name, table,
                    )
                    return 1

                else:  # sqlite via SQLAlchemy
                    conn.exec_driver_sql(f"PRAGMA table_info({table})")
                    if _sqlite_column_exists(conn, table, col_name):
                        logger.info("Column %s.%s already exists — no-op.", table, col_name)
                        return 0

                    conn.exec_driver_sql(
                        f"ALTER TABLE {table} ADD COLUMN {col_name} BOOLEAN NOT NULL DEFAULT 1"
                    )
                    conn.commit()
                    logger.info(
                        "✅ Added '%s' column to %s (SQLite, default: True).",
                        col_name, table,
                    )
                    return 1

        except Exception as exc:
            logger.warning(
                "SQLAlchemy connection failed (%s). Falling back to sqlite3.", exc
            )

    # ── Step 2: SQLite fallback (legacy/dev mode) ───────────────────────────
    if not os.path.exists(DB_PATH):
        logger.error(
            "Database not found at %s. "
            "Set DATABASE_URL env var or run the app first to create it.",
            DB_PATH,
        )
        sys.exit(1)

    conn = sqlite3.connect(DB_PATH)
    try:
        if _sqlite_column_exists(conn, table, col_name):
            logger.info("Column %s.%s already exists — no-op.", table, col_name)
            return 0

        conn.execute(
            f"ALTER TABLE {table} ADD COLUMN {col_name} BOOLEAN NOT NULL DEFAULT 1"
        )
        conn.commit()
        logger.info(
            "✅ Added '%s' column to %s (SQLite, default: True).",
            col_name, table,
        )
        return 1
    finally:
        conn.close()


def run() -> int:
    try:
        added = migrate()
        if added:
            logger.warning("⚠️ %d column(s) added. Redeploy recommended.", added)
        else:
            logger.info("Migration complete — nothing to do.")
        return 0
    except Exception as exc:
        logger.exception("Migration failed: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(run())
