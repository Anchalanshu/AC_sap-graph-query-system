from __future__ import annotations

import json
import os
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, StreamingResponse
from pydantic import BaseModel

from database import db_session, get_schema_text, init_db
from graph_builder import export_graph_json
from llm_service import query_llm, stream_answer_words


app = FastAPI(title="Dodge AI — ERP Graph Explorer")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class QueryRequest(BaseModel):
    question: str
    history: list[dict[str, Any]] = []


@app.on_event("startup")
def _startup() -> None:
    # Ensure db file + schema exists (ingest populates data)
    with db_session() as conn:
        init_db(conn)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/schema", response_class=PlainTextResponse)
def schema():
    with db_session() as conn:
        return get_schema_text(conn)


@app.get("/api/graph")
def graph():
    # Limit large graphs to keep frontend fast
    return export_graph_json(limit_nodes=200)


@app.post("/api/query")
async def query(req: QueryRequest):
    try:
        out = await query_llm(req.question, req.history or [])
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {
        "answer": out.get("answer", ""),
        "sql": out.get("sql"),
        "results": out.get("result", []),
        "highlighted_nodes": out.get("highlighted_nodes", []),
        "is_domain_relevant": bool(out.get("is_domain_relevant", False)),
        "explanation": out.get("explanation", ""),
        "graph": out.get("graph", {"nodes": [], "edges": []}),
        "graph_explanation": out.get("graph_explanation", ""),
    }


@app.post("/api/query/stream")
async def query_stream(req: QueryRequest):
    async def event_gen():
        try:
            async for ev in stream_answer_words(req.question, req.history or []):
                yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type':'error','error':str(e)})}\n\n"

    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
    }
    return StreamingResponse(event_gen(), media_type="text/event-stream", headers=headers)

