## Dodge AI — ERP Graph Explorer

Graph-based data modeling + query system for a SAP ERP Sales Order Items dataset (JSONL → SQLite → NetworkX graph + LLM-assisted SQL Q&A).

### Quickstart

#### 1) Backend (FastAPI + SQLite + NetworkX + Gemini)

From the repo root:

```bash
cd backend
pip install -r requirements.txt
python ingest.py
$env:GEMINI_API_KEY="YOUR_KEY_HERE"
uvicorn main:app --reload --port 8001
```

Notes:
- **Dataset**: already copied to `backend/data/dataset.jsonl` (79 records).
- **Database**: created at `backend/database.db`.

Health check:
- `http://localhost:8001/health`

#### 2) Frontend (React + Vite + TypeScript + Tailwind)

In a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Open:
- `http://localhost:5173`

### Architecture decisions

- **SQLite-first**: the source of truth is `database.db` for reliable aggregation + filtering.
- **NetworkX graph**: graph is derived from SQLite and exported as `{ nodes, links }` for the UI.
- **Stable graph IDs** (prevents collisions):
  - SalesOrder: `SO:<6digit>` (example `SO:740506`)
  - SalesOrderItem: `SOI:<salesOrder>-<item>` (example `SOI:740506-10`)
  - Material: `MAT:<material>` (example `MAT:S8907367001003`)
  - Plant: `PLANT:<plantId>` (example `PLANT:1920`)
  - MaterialGroup: `MG:<group>` (example `MG:ZFG1001`)
- **Graph limiting**: to keep the UI responsive, graph export caps at **150 nodes** (with induced edges).

### LLM prompting strategy

The backend uses a strict, fixed **system prompt** that:
- Forces **dataset-only** behavior
- Forces **SQLite SQL generation**
- Forces a **JSON contract**: `{ sql, explanation, is_domain_relevant }`

Execution flow:
- Gemini generates SQL JSON
- Backend validates SQL (**SELECT-only**) and runs it on SQLite
- Gemini formats a natural language answer from the SQL result
- Backend extracts entity IDs (sales orders/materials) from the answer to highlight nodes

### Guardrails (two levels)

- **Level 1 (fast keyword check)**: if the question contains none of the SAP/ERP keywords, backend immediately responds with:
  - `"This system is designed to answer questions related to the provided SAP ERP dataset only."`
- **Level 2 (LLM system prompt)**: Gemini is instructed to return the exact same guardrail message for non-domain questions.

The UI renders guardrail responses with an **orange/red border**.

### Streaming responses

The frontend uses a streaming endpoint:
- `POST /api/query/stream` (Server-Sent Events over a streaming fetch)

The backend streams the answer **word-by-word** to create a smooth “typing” effect.

### Files generated

Backend:
- `backend/ingest.py`: JSONL → SQLite ingestion + summary
- `backend/database.py`: DB utilities + schema init
- `backend/graph_builder.py`: NetworkX builder + JSON exporter
- `backend/llm_service.py`: Gemini SQL planning + execution + highlighting + streaming
- `backend/main.py`: FastAPI API (graph/schema/query/stream/health)

Frontend:
- `frontend/src/App.tsx`: split layout + toast + inspector integration
- `frontend/src/components/GraphView.tsx`: `react-force-graph-2d` rendering + legend + pulse highlight + controls
- `frontend/src/components/ChatPanel.tsx`: streaming chat, SQL accordion, suggested chips, export to markdown
- `frontend/src/components/NodeInspector.tsx`: slide-in inspector with properties + related nodes

