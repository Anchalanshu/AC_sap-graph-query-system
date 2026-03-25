from __future__ import annotations

import json
import os
from collections import defaultdict
from typing import Any

from database import DB_PATH, db_session, init_db


DATASET_PATH = os.path.join(os.path.dirname(__file__), "data", "dataset.jsonl")
SALES_ORDER_HEADERS_PATH = os.path.join(
    os.path.dirname(__file__), "data", "sales_order_headers.jsonl"
)
OUTBOUND_DELIVERY_HEADERS_PATH = os.path.join(
    os.path.dirname(__file__), "data", "outbound_delivery_headers.jsonl"
)
OUTBOUND_DELIVERY_ITEMS_PATHS = [
    os.path.join(os.path.dirname(__file__), "data", "outbound_delivery_items_1.jsonl"),
    os.path.join(os.path.dirname(__file__), "data", "outbound_delivery_items_2.jsonl"),
]


def _to_float(val: Any) -> float | None:
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip()
    if s == "":
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _to_text(val: Any) -> str:
    if val is None:
        return ""
    return str(val)


def main() -> None:
    # Always rebuild database from scratch to prevent partial ingestion issues.
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    if not os.path.exists(DATASET_PATH):
        raise FileNotFoundError(f"Dataset not found at {DATASET_PATH}")

    records: list[dict[str, Any]] = []
    with open(DATASET_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            records.append(json.loads(line))

    sales_orders_in_items = {_to_text(r.get("salesOrder")) for r in records if r.get("salesOrder")}

    totals_by_order: dict[str, float] = defaultdict(float)
    currency_by_order: dict[str, str] = {}
    materials: dict[str, str] = {}
    plants: set[str] = set()
    customers_by_order: dict[str, str] = {}
    deliveries_by_order: dict[str, set[str]] = defaultdict(set)
    deliveries_shipping_point: dict[str, str] = {}

    for r in records:
        so = _to_text(r.get("salesOrder"))
        currency = _to_text(r.get("transactionCurrency"))
        net_amount = _to_float(r.get("netAmount")) or 0.0
        totals_by_order[so] += net_amount
        if so not in currency_by_order:
            currency_by_order[so] = currency
        if r.get("material"):
            materials[_to_text(r.get("material"))] = _to_text(r.get("materialGroup"))
        if r.get("productionPlant"):
            plants.add(_to_text(r.get("productionPlant")))

    # Optional: sales_order_headers → Customer places SalesOrder
    if os.path.exists(SALES_ORDER_HEADERS_PATH):
        with open(SALES_ORDER_HEADERS_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                h = json.loads(line)
                so = _to_text(h.get("salesOrder"))
                if so and so in sales_orders_in_items:
                    sold_to = _to_text(h.get("soldToParty"))
                    if sold_to:
                        customers_by_order[so] = sold_to

    # Optional: outbound delivery headers
    if os.path.exists(OUTBOUND_DELIVERY_HEADERS_PATH):
        with open(OUTBOUND_DELIVERY_HEADERS_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                d = json.loads(line)
                doc = _to_text(d.get("deliveryDocument"))
                sp = _to_text(d.get("shippingPoint"))
                if doc:
                    deliveries_shipping_point[doc] = sp

    # Optional: outbound delivery items → SalesOrder delivered_by Delivery
    for p in OUTBOUND_DELIVERY_ITEMS_PATHS:
        if not os.path.exists(p):
            continue
        with open(p, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                it = json.loads(line)
                so = _to_text(it.get("referenceSdDocument"))
                doc = _to_text(it.get("deliveryDocument"))
                if so and doc and so in sales_orders_in_items:
                    deliveries_by_order[so].add(doc)

    with db_session() as conn:
        init_db(conn)
        # Use a single transaction for all inserts to avoid partial ingestion.
        # Insert parent tables first
        conn.executemany(
            "INSERT INTO plants (plant_id) VALUES (?)",
            [(p,) for p in sorted(plants)],
        )

        conn.executemany(
            "INSERT INTO materials (material, material_group) VALUES (?, ?)",
            [(m, mg) for m, mg in materials.items()],
        )

        customers = sorted({c for c in customers_by_order.values() if c})
        if customers:
            conn.executemany(
                "INSERT INTO customers (customer_id) VALUES (?)",
                [(c,) for c in customers],
            )

        # Sales orders (parent for items and mappings)
        conn.executemany(
            "INSERT INTO sales_orders (sales_order, transaction_currency, total_net_amount) VALUES (?, ?, ?)",
            [(so, currency_by_order.get(so, ""), float(total)) for so, total in totals_by_order.items()],
        )

        # Sales order headers + mapping table
        if customers_by_order:
            conn.executemany(
                "INSERT INTO sales_order_headers (sales_order, sold_to_party, transaction_currency, total_net_amount) VALUES (?, ?, ?, ?)",
                [
                    (
                        so,
                        customers_by_order.get(so, ""),
                        currency_by_order.get(so, ""),
                        float(totals_by_order.get(so, 0.0)),
                    )
                    for so in sorted(totals_by_order.keys())
                ],
            )
            conn.executemany(
                "INSERT INTO sales_order_customers (sales_order, customer_id) VALUES (?, ?)",
                [(so, cust) for so, cust in customers_by_order.items()],
            )

        # Deliveries + mapping
        all_delivery_docs = sorted({d for ds in deliveries_by_order.values() for d in ds})
        if all_delivery_docs:
            conn.executemany(
                "INSERT INTO deliveries (delivery_document, shipping_point) VALUES (?, ?)",
                [(d, deliveries_shipping_point.get(d, "")) for d in all_delivery_docs],
            )
            conn.executemany(
                "INSERT INTO sales_order_deliveries (sales_order, delivery_document) VALUES (?, ?)",
                [(so, d) for so, ds in deliveries_by_order.items() for d in sorted(ds)],
            )

        # Finally, sales order items
        conn.executemany(
            """
            INSERT INTO sales_order_items (
              sales_order,
              sales_order_item,
              item_category,
              material,
              requested_quantity,
              quantity_unit,
              net_amount,
              material_group,
              production_plant,
              storage_location,
              rejection_reason,
              billing_block_reason
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    _to_text(r.get("salesOrder")),
                    _to_text(r.get("salesOrderItem")),
                    _to_text(r.get("salesOrderItemCategory")),
                    _to_text(r.get("material")),
                    _to_float(r.get("requestedQuantity")),
                    _to_text(r.get("requestedQuantityUnit")),
                    _to_float(r.get("netAmount")),
                    _to_text(r.get("materialGroup")),
                    _to_text(r.get("productionPlant")),
                    _to_text(r.get("storageLocation")),
                    _to_text(r.get("salesDocumentRjcnReason")),
                    _to_text(r.get("itemBillingBlockReason")),
                )
                for r in records
            ],
        )

        conn.commit()

        num_orders = conn.execute("SELECT COUNT(*) AS c FROM sales_orders").fetchone()["c"]
        num_items = conn.execute("SELECT COUNT(*) AS c FROM sales_order_items").fetchone()["c"]
        num_materials = conn.execute("SELECT COUNT(*) AS c FROM materials").fetchone()["c"]
        num_plants = conn.execute("SELECT COUNT(*) AS c FROM plants").fetchone()["c"]
        num_customers = conn.execute("SELECT COUNT(*) AS c FROM customers").fetchone()["c"]
        num_deliveries = conn.execute("SELECT COUNT(*) AS c FROM deliveries").fetchone()["c"]
        total_net = conn.execute("SELECT SUM(total_net_amount) AS s FROM sales_orders").fetchone()["s"]

    print("Ingestion complete.")
    print(f"- Database: {DB_PATH}")
    print(f"- Records read: {len(records)}")
    print(f"- Sales orders: {num_orders}")
    print(f"- Sales order items: {num_items}")
    print(f"- Materials: {num_materials}")
    print(f"- Plants: {num_plants}")
    print(f"- Customers: {num_customers}")
    print(f"- Deliveries: {num_deliveries}")
    print(f"- Total net amount (all orders): {float(total_net or 0.0):.2f}")


if __name__ == "__main__":
    main()

