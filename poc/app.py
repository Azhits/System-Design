"""
FastAPI demo application for the support ticket automation PoC.

Exposes:
  POST /tickets            - submit a raw ticket {ticket_id, text} and get the pipeline decision
  GET  /tickets/mock       - load and process all mock tickets from data/mock_tickets.json
  GET  /decisions          - read the audit log (logs/decisions.jsonl)
  GET  /health             - simple health/degradation status
  GET  /                   - serves static/index.html demo UI

Run with: uvicorn poc.app:app --reload
Or simply: python poc/run_demo.py
"""
import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from . import pipeline
from . import degradation

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
STATIC_DIR = BASE_DIR / "static"
LOG_PATH = BASE_DIR / "logs" / "decisions.jsonl"

app = FastAPI(title="Support Ticket Automation PoC")

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


class TicketIn(BaseModel):
    ticket_id: str
    text: str


@app.get("/")
def index():
    index_path = STATIC_DIR / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path))
    raise HTTPException(status_code=404, detail="static/index.html not found")


@app.get("/health")
def health(queue_size: int = 0, llm_available: bool = True):
    deg = degradation.get_level(queue_size=queue_size, llm_available=llm_available)
    return {"status": "ok", "degradation": deg}


@app.post("/tickets")
def submit_ticket(ticket: TicketIn, queue_size: int = 0, llm_available: bool = True):
    record = pipeline.process_ticket(
        ticket.dict(), queue_size=queue_size, llm_available=llm_available
    )
    return record


@app.get("/tickets/mock")
def process_mock_tickets(queue_size: int = 0, llm_available: bool = True):
    mock_path = DATA_DIR / "mock_tickets.json"
    if not mock_path.exists():
        raise HTTPException(status_code=404, detail="data/mock_tickets.json not found")
    with open(mock_path, encoding="utf-8") as f:
        tickets = json.load(f)
    results = [
        pipeline.process_ticket(t, queue_size=queue_size, llm_available=llm_available)
        for t in tickets
    ]
    return results


@app.get("/decisions")
def get_decisions(limit: int = 100):
    if not LOG_PATH.exists():
        return []
    lines = LOG_PATH.read_text(encoding="utf-8").strip().splitlines()
    records = [json.loads(line) for line in lines[-limit:]]
    return records
