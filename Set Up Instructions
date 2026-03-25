Setup Instructions
1. Clone the repository
git clone https://github.com/Anchalanshu/AC_sap-graph-query-system.git
cd AC_sap-graph-query-system

2. Backend Setup (FastAPI)
cd backend
pip install -r requirements.txt
python ingest.py
Set your Gemini API key:
set GEMINI_API_KEY=YOUR_API_KEY

Run the backend server:
uvicorn main:app --reload --port 8001
Backend will run at:
http://127.0.0.1:8000/docs
Health check:
http://localhost:8001/health

3. Frontend Setup (React + Vite)
Open a second terminal:
cd frontend
npm install
npm run dev
Frontend will run at:
http://localhost:5173

4. Usage
Ask a natural language question about the SAP dataset.
The backend converts the question into SQL using Gemini.
SQL runs on SQLite database.
Results are visualized as a graph.
