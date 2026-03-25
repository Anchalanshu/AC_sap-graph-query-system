from __future__ import annotations

from typing import Any

from database import db_session


def _nid(prefix: str, value: str) -> str:
    return f"{prefix}:{value}"


def export_graph_json(limit_nodes: int = 200) -> dict[str, Any]:
    """
    Returns ONLY:
    {
      "nodes": [{"id","label","type"}],
      "edges": [{"source","target","label"}]
    }

    Types: Customer | SalesOrder | Material | Plant | Delivery
    Relationships:
      Customer -> placed -> SalesOrder
      SalesOrder -> contains -> Material
      Material -> produced_in -> Plant
      SalesOrder -> delivered_by -> Delivery
    """
    nodes: dict[str, dict[str, str]] = {}
    edges: list[dict[str, str]] = []

    def add_node(nid: str, label: str, type_: str) -> None:
        if nid not in nodes:
            nodes[nid] = {"id": nid, "label": label, "type": type_}

    def add_edge(source: str, target: str, label: str) -> None:
        edges.append({"source": source, "target": target, "label": label})

    with db_session() as conn:
        # Customer -> placed -> SalesOrder
        for r in conn.execute(
            "SELECT sales_order, customer_id FROM sales_order_customers"
        ).fetchall():
            so = str(r["sales_order"])
            cust = str(r["customer_id"])
            so_id = _nid("SO", so)
            cust_id = _nid("CUST", cust)
            add_node(cust_id, cust, "Customer")
            add_node(so_id, so, "SalesOrder")
            add_edge(cust_id, so_id, "placed")

        # SalesOrder -> contains -> Material and Material -> produced_in -> Plant
        for r in conn.execute(
            """
            SELECT DISTINCT sales_order, material, production_plant
            FROM sales_order_items
            """
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
            "SELECT DISTINCT sales_order, delivery_document FROM sales_order_deliveries"
        ).fetchall():
            so = str(r["sales_order"])
            doc = str(r["delivery_document"])
            so_id = _nid("SO", so)
            del_id = _nid("DEL", doc)
            add_node(so_id, so, "SalesOrder")
            add_node(del_id, doc, "Delivery")
            add_edge(so_id, del_id, "delivered_by")

    node_list = list(nodes.values())
    if len(node_list) > limit_nodes:
        node_list = node_list[:limit_nodes]
        allowed = {n["id"] for n in node_list}
        edges = [e for e in edges if e["source"] in allowed and e["target"] in allowed]

    return {"nodes": node_list, "edges": edges}

