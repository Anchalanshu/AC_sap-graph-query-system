from __future__ import annotations

import asyncio
import json
import os
import re
from typing import Any

from dotenv import load_dotenv

from database import db_session, execute_sql, get_schema_text
from graph_query import build_graph_response_for_query

def _load_env() -> None:
    # Support running from backend/ while .env sits at repo root.
    here = os.path.dirname(__file__)
    candidates = [
        os.path.join(here, ".env"),
        os.path.join(here, "..", ".env"),
        os.path.join(here, "..", ".env.local"),
    ]
    for p in candidates:
        if os.path.exists(p):
            load_dotenv(dotenv_path=p, override=False)
            return
    load_dotenv(override=False)


_load_env()


SYSTEM_PROMPT = """
You are a data analyst for a SAP ERP system. You have access to a SQLite database 
with these tables:

sales_orders: sales_order (PK), transaction_currency, total_net_amount
sales_order_headers: sales_order (PK), sold_to_party, transaction_currency, total_net_amount
sales_order_items: id, sales_order (FK), sales_order_item, item_category, material, 
  requested_quantity, quantity_unit, net_amount, material_group, production_plant, 
  storage_location, rejection_reason, billing_block_reason
customers: customer_id (PK)
materials: material (PK), material_group
plants: plant_id (PK)
deliveries: delivery_document (PK), shipping_point
sales_order_customers: sales_order (PK), customer_id
sales_order_deliveries: id, sales_order, delivery_document

RULES:
1. ONLY answer questions about this SAP ERP dataset
2. If asked anything unrelated (general knowledge, creative writing, math, jokes, 
   personal questions, etc.) respond EXACTLY: "This system is designed to answer 
   questions related to the provided SAP ERP dataset only."
3. Always generate a valid SQLite SQL query to answer the question
4. Return response as JSON: {"sql": "...", "explanation": "...", "is_domain_relevant": true/false}
5. If not domain relevant, return: {"sql": null, "explanation": "This system is designed to answer questions related to the provided SAP ERP dataset only.", "is_domain_relevant": false}

DOMAIN KEYWORDS that are relevant: order, sales, material, plant, delivery, invoice, 
billing, quantity, amount, product, item, storage, currency, rejection, block, group
""".strip()


ALLOWED_KEYWORDS = [
    "order",
    "sales",
    "material",
    "plant",
    "delivery",
    "invoice",
    "billing",
    "quantity",
    "amount",
    "product",
    "item",
    "storage",
    "currency",
    "rejection",
    "block",
    "group",
    "sap",
    "erp",
]


_RE_SALES_ORDER = re.compile(r"\b\d{6}\b")
_RE_MATERIAL = re.compile(r"\bS[A-Za-z0-9]+\b")


def fast_guardrail(question: str) -> bool:
    q = question.lower()
    return any(k in q for k in ALLOWED_KEYWORDS)


def _ensure_select_only(sql: str) -> str:
    s = (sql or "").strip().rstrip(";").strip()
    if not s:
        raise ValueError("Empty SQL")
    lowered = s.lower()
    if not lowered.startswith("select") and not lowered.startswith("with"):
        raise ValueError("Only SELECT queries are allowed")
    forbidden = ["insert", "update", "delete", "drop", "alter", "create", "attach", "pragma"]
    if any(f in lowered for f in forbidden):
        raise ValueError("Unsafe SQL detected")
    return s


def _extract_highlights(text: str) -> list[str]:
    sales_orders = set(_RE_SALES_ORDER.findall(text or ""))
    materials = set(_RE_MATERIAL.findall(text or ""))
    out: list[str] = []
    for so in sorted(sales_orders):
        out.append(f"SO:{so}")
    for m in sorted(materials):
        out.append(f"MAT:{m}")
    return out


def _parse_json_response(raw: str) -> dict[str, Any]:
    raw = (raw or "").strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # try to find a JSON object in the text
        m = re.search(r"\{[\s\S]*\}", raw)
        if not m:
            raise
        return json.loads(m.group(0))


def _gemini_client():
    import google.generativeai as genai

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "Missing GEMINI_API_KEY. Set it in your environment or create a .env file "
            "with GEMINI_API_KEY=... (repo root or backend/)."
        )

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(
        model_name="gemini-1.5-flash",
        system_instruction=SYSTEM_PROMPT,
        generation_config={
            "temperature": 0.2,
            "response_mime_type": "application/json",
        },
    )
    return model


def _history_to_text(conversation_history: list) -> str:
    # expected shape: [{"role":"user"|"ai", "content": "..."}]
    lines: list[str] = []
    for m in conversation_history[-8:]:
        role = str(m.get("role", "user")).lower()
        content = str(m.get("content", ""))
        if not content:
            continue
        lines.append(f"{role.upper()}: {content}")
    return "\n".join(lines).strip()


async def _call_gemini_json(prompt: str) -> dict[str, Any]:
    model = _gemini_client()

    def _run() -> dict[str, Any]:
        resp = model.generate_content(prompt)
        return _parse_json_response(getattr(resp, "text", "") or "")

    return await asyncio.to_thread(_run)


async def _call_gemini_text(prompt: str) -> str:
    model = _gemini_client()

    def _run() -> str:
        resp = model.generate_content(prompt)
        return (getattr(resp, "text", "") or "").strip()

    return await asyncio.to_thread(_run)


async def query_llm(user_question: str, conversation_history: list) -> dict:
    """
    Returns:
      {
        "sql": str|None,
        "result": list,
        "answer": str,
        "highlighted_nodes": list[str],
        "is_domain_relevant": bool
      }
    """
    if not fast_guardrail(user_question):
        msg = "This system is designed to answer questions related to the provided SAP ERP dataset only."
        return {
            "sql": None,
            "result": [],
            "answer": msg,
            "highlighted_nodes": [],
            "is_domain_relevant": False,
            "explanation": msg,
            "graph": {"nodes": [], "edges": []},
        }

    history_text = _history_to_text(conversation_history)

    with db_session() as conn:
        schema = get_schema_text(conn)

    planning_prompt = (
        "Given the database schema below, write a single SQLite SQL query that answers the user question.\n"
        "Return ONLY JSON with keys: sql, explanation, is_domain_relevant.\n\n"
        f"SCHEMA:\n{schema}\n\n"
        f"CONVERSATION (most recent last):\n{history_text}\n\n"
        f"USER QUESTION:\n{user_question}\n"
    )

    plan = await _call_gemini_json(planning_prompt)

    if not plan.get("is_domain_relevant", False):
        msg = "This system is designed to answer questions related to the provided SAP ERP dataset only."
        return {
            "sql": None,
            "result": [],
            "answer": msg,
            "highlighted_nodes": [],
            "is_domain_relevant": False,
            "explanation": msg,
            "graph": {"nodes": [], "edges": []},
        }

    sql = plan.get("sql")
    explanation = str(plan.get("explanation", "")).strip()
    try:
        sql = _ensure_select_only(str(sql))
    except Exception:
        msg = "This system is designed to answer questions related to the provided SAP ERP dataset only."
        return {
            "sql": None,
            "result": [],
            "answer": msg,
            "highlighted_nodes": [],
            "is_domain_relevant": False,
            "explanation": msg,
            "graph": {"nodes": [], "edges": []},
        }

    with db_session() as conn:
        result = execute_sql(conn, sql)

    format_prompt = (
        "You are answering a question about a SAP ERP dataset.\n"
        "Use the SQL result to produce a clear, concise answer.\n"
        "When you mention a sales order, include the 6-digit sales_order value (e.g. 740506).\n"
        "When you mention a material, include the full material id (e.g. S8907367001003).\n\n"
        f"USER QUESTION:\n{user_question}\n\n"
        f"SQL:\n{sql}\n\n"
        f"RESULT (JSON):\n{json.dumps(result, ensure_ascii=False)}\n"
    )

    answer = await _call_gemini_text(format_prompt)
    highlighted_nodes = _extract_highlights(answer)
    graph = build_graph_response_for_query(sql=sql, result_rows=result)

    return {
        "sql": sql,
        "result": result,
        "answer": answer,
        "highlighted_nodes": highlighted_nodes,
        "is_domain_relevant": True,
        "explanation": explanation,
        "graph": {"nodes": graph["nodes"], "edges": graph["edges"]},
        "graph_explanation": graph.get("explanation", ""),
    }


async def stream_answer_words(user_question: str, conversation_history: list):
    """
    Async generator yielding word-ish chunks for SSE streaming.
    Yields dict events:
      {"type":"meta", ...}
      {"type":"token","token":"..."}
      {"type":"done", ...full payload...}
    """
    if not fast_guardrail(user_question):
        msg = "This system is designed to answer questions related to the provided SAP ERP dataset only."
        yield {
            "type": "done",
            "payload": {
                "answer": msg,
                "sql": None,
                "results": [],
                "highlighted_nodes": [],
                "is_domain_relevant": False,
                "explanation": msg,
                "graph": {"nodes": [], "edges": []},
                "graph_explanation": "",
            },
        }
        return

    # First do the JSON planning + SQL execution (non-streaming; small)
    payload = await query_llm(user_question, conversation_history)

    # Stream the already-computed answer word-by-word (keeps UI smooth and deterministic)
    yield {
        "type": "meta",
        "payload": {
            "sql": payload.get("sql"),
            "results": payload.get("result", []),
            "is_domain_relevant": payload.get("is_domain_relevant", False),
            "explanation": payload.get("explanation", ""),
            "highlighted_nodes": payload.get("highlighted_nodes", []),
            "graph": payload.get("graph", {"nodes": [], "edges": []}),
            "graph_explanation": payload.get("graph_explanation", ""),
        },
    }

    text = str(payload.get("answer", ""))
    words = re.split(r"(\s+)", text)
    for w in words:
        if w == "":
            continue
        yield {"type": "token", "token": w}

    yield {
        "type": "done",
        "payload": {
            "answer": text,
            "sql": payload.get("sql"),
            "results": payload.get("result", []),
            "highlighted_nodes": payload.get("highlighted_nodes", []),
            "is_domain_relevant": payload.get("is_domain_relevant", False),
            "explanation": payload.get("explanation", ""),
            "graph": payload.get("graph", {"nodes": [], "edges": []}),
            "graph_explanation": payload.get("graph_explanation", ""),
        },
    }

