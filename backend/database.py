from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from typing import Any, Iterable


DB_PATH = os.path.join(os.path.dirname(__file__), "database.db")


def get_connection(db_path: str | None = None) -> sqlite3.Connection:
    path = db_path or DB_PATH
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def db_session(db_path: str | None = None) -> Iterable[sqlite3.Connection]:
    conn = get_connection(db_path)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA foreign_keys = ON;")

    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS plants (
          plant_id TEXT PRIMARY KEY
        );

        CREATE TABLE IF NOT EXISTS materials (
          material TEXT PRIMARY KEY,
          material_group TEXT
        );

        CREATE TABLE IF NOT EXISTS customers (
          customer_id TEXT PRIMARY KEY
        );

        CREATE TABLE IF NOT EXISTS sales_orders (
          sales_order TEXT PRIMARY KEY,
          transaction_currency TEXT,
          total_net_amount REAL
        );

        -- Compatibility tables matching SAP O2C naming
        CREATE TABLE IF NOT EXISTS sales_order_headers (
          sales_order TEXT PRIMARY KEY,
          sold_to_party TEXT,
          transaction_currency TEXT,
          total_net_amount REAL,
          FOREIGN KEY (sales_order) REFERENCES sales_orders(sales_order),
          FOREIGN KEY (sold_to_party) REFERENCES customers(customer_id)
        );

        CREATE TABLE IF NOT EXISTS sales_order_items (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          sales_order TEXT,
          sales_order_item TEXT,
          item_category TEXT,
          material TEXT,
          requested_quantity REAL,
          quantity_unit TEXT,
          net_amount REAL,
          material_group TEXT,
          production_plant TEXT,
          storage_location TEXT,
          rejection_reason TEXT,
          billing_block_reason TEXT,
          FOREIGN KEY (sales_order) REFERENCES sales_orders(sales_order)
        );

        CREATE TABLE IF NOT EXISTS deliveries (
          delivery_document TEXT PRIMARY KEY,
          shipping_point TEXT
        );

        CREATE TABLE IF NOT EXISTS sales_order_customers (
          sales_order TEXT PRIMARY KEY,
          customer_id TEXT,
          FOREIGN KEY (sales_order) REFERENCES sales_orders(sales_order),
          FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
        );

        CREATE TABLE IF NOT EXISTS sales_order_deliveries (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          sales_order TEXT,
          delivery_document TEXT,
          FOREIGN KEY (sales_order) REFERENCES sales_orders(sales_order),
          FOREIGN KEY (delivery_document) REFERENCES deliveries(delivery_document)
        );
        """
    )


def get_schema_text(conn: sqlite3.Connection) -> str:
    rows = conn.execute(
        "SELECT name, sql FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    parts: list[str] = []
    for r in rows:
        name = r["name"]
        sql = r["sql"] or ""
        parts.append(f"-- {name}\n{sql}\n")
    return "\n".join(parts).strip() + "\n"


def execute_sql(conn: sqlite3.Connection, sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    cur = conn.execute(sql, params or {})
    rows = cur.fetchall()
    return [dict(r) for r in rows]

