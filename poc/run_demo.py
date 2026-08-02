"""
Convenience entry point to run the demo API + web UI locally.

Usage:
    python poc/run_demo.py

Then open http://127.0.0.1:8000 in a browser to use the demo UI,
or call the API directly, e.g.:
    curl http://127.0.0.1:8000/tickets/mock
"""
import uvicorn

if __name__ == "__main__":
    uvicorn.run("poc.app:app", host="127.0.0.1", port=8000, reload=True)
