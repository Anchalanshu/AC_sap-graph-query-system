from __future__ import annotations

from typing import Any, Iterable

from database import db_session, execute_sql


def _node(id_: str, label: str, type_: str) -> dict[str, str]:
    return {"id": id_, "label": label, "type": type_}


def _edge(source: str, target: str, label: str) -> dict[str, str]:
    return {"source": source, "target": target, "label": label}


def _nid(prefix: str, value: str) -> str:
    return f"{prefix}:{value}"


def _collect_ids_from_result(rows: list[dict[str, Any]]) -> dict[str, set[str]]:
    """
    Heuristic: look for common column names in SQL result and collect IDs.
    """
    keys_map = {
        "sales_order": "so",
        "salesOrder": "so",
        "material": "mat",
        "production_plant": "plant",
        "plant_id": "plant",
        "customer_id": "cust",
        "soldToParty": "cust",
        "delivery_document": "del",
        "deliveryDocument": "del",
    }

    out: dict[str, set[str]] = {"so": set(), "mat": set(), "plant": set(), "cust": set(), "del": set()}
    for r in rows:
        for k, v in r.items():
            if v is None:
                continue
            bucket = keys_map.get(k)
            if not bucket:
                continue
            s = str(v).strip()
            if s:
                out[bucket].add(s)
    return out


def build_graph_response_for_query(
    sql: str | None,
    result_rows: list[dict[str, Any]],
    limit_nodes: int = 180,
) -> dict[str, Any]:
    """
    Returns:
    {
      "nodes": [{id,label,type}],
      "edges": [{source,target,label}],
      "explanation": str
    }

    Types are constrained to: Customer | SalesOrder | Material | Plant | Delivery
    """
    ids = _collect_ids_from_result(result_rows)

    nodes: dict[str, dict[str, str]] = {}
    edges: list[dict[str, str]] = []

    def add_node(nid: str, label: str, type_: str):
        if nid not in nodes:
            nodes[nid] = _node(nid, label, type_)

    def add_edge(s: str, t: str, label: str):
        edges.append(_edge(s, t, label))

    with db_session() as conn:
        # Expand sales orders
        sales_orders = sorted(ids["so"])
        if sales_orders:
            q_marks = ",".join(["?"] * len(sales_orders))
            # Customer -> places -> SalesOrder
            for r in conn.execute(
                f"""
                SELECT soc.sales_order, soc.customer_id
                FROM sales_order_customers soc
                WHERE soc.sales_order IN ({q_marks})
                """,
                sales_orders,
            ).fetchall():
                so = str(r["sales_order"])
                cust = str(r["customer_id"])
                so_id = _nid("SO", so)
                cust_id = _nid("CUST", cust)
                add_node(cust_id, cust, "Customer")
                add_node(so_id, so, "SalesOrder")
                add_edge(cust_id, so_id, "placed")

            # SalesOrder -> contains -> Material (+ Material -> stored_in -> Plant)
            for r in conn.execute(
                f"""
                SELECT DISTINCT sales_order, material, production_plant
                FROM sales_order_items
                WHERE sales_order IN ({q_marks})
                """,
                sales_orders,
            ).fetchall():
                so = str(r["sales_order"])
                mat = str(r["material"])
                plant = str(r["production_plant"])
                so_id = _nid("SO", so)
                mat_id = _nid("MAT", mat)
                plant_id = _nid("PLANT", plant)
                add_node(so_id, so, "SalesOrder")
                add_node(mat_id, mat, "Material")
                add_node(plant_id, plant, "Plant")
                add_edge(so_id, mat_id, "contains")
                add_edge(mat_id, plant_id, "produced_in")

            # SalesOrder -> delivered_by -> Delivery
            for r in conn.execute(
                f"""
                SELECT DISTINCT sod.sales_order, sod.delivery_document
                FROM sales_order_deliveries sod
                WHERE sod.sales_order IN ({q_marks})
                """,
                sales_orders,
            ).fetchall():
                so = str(r["sales_order"])
                doc = str(r["delivery_document"])
                so_id = _nid("SO", so)
                del_id = _nid("DEL", doc)
                add_node(so_id, so, "SalesOrder")
                add_node(del_id, doc, "Delivery")
                add_edge(so_id, del_id, "delivered_by")

        # Expand materials asked directly
        materials = sorted(ids["mat"])
        if materials:
            q_marks = ",".join(["?"] * len(materials))
            for r in conn.execute(
                f"""
                SELECT DISTINCT material, production_plant
                FROM sales_order_items
                WHERE material IN ({q_marks})
                """,
                materials,
            ).fetchall():
                mat = str(r["material"])
                plant = str(r["production_plant"])
                mat_id = _nid("MAT", mat)
                plant_id = _nid("PLANT", plant)
                add_node(mat_id, mat, "Material")
                add_node(plant_id, plant, "Plant")
                add_edge(mat_id, plant_id, "produced_in")

    # Hard cap nodes for UI
    node_list = list(nodes.values())
    if len(node_list) > limit_nodes:
        node_list = node_list[:limit_nodes]
        allowed = {n["id"] for n in node_list}
        edges = [e for e in edges if e["source"] in allowed and e["target"] in allowed]

    explanation = (
        "Built a relationship subgraph using these ERP links: "
        "Customer → placed → SalesOrder, SalesOrder → contains → Material, "
        "Material → produced_in → Plant, SalesOrder → delivered_by → Delivery."
    )
    if sql:
        explanation += " The subgraph is derived from the entities returned by the SQL query."

    return {"nodes": node_list, "edges": edges, "explanation": explanation}

