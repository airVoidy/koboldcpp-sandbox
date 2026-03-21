"""Start the DataStore API server standalone."""
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.kobold_sandbox.data_store.api import create_datastore_router

def create_datastore_app():
    app = FastAPI(title="DataStore API")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    datastore_root = project_root / ".sandbox" / "datastore"
    app.include_router(create_datastore_router(datastore_root), prefix="/api/datastore")

    @app.get("/")
    def root():
        return {"service": "DataStore API", "docs": "/docs"}

    return app

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=5002)
    parser.add_argument("--host", type=str, default="0.0.0.0")
    args = parser.parse_args()

    print(f"Starting DataStore API on http://{args.host}:{args.port}")
    print(f"Docs: http://localhost:{args.port}/docs")
    print(f"DataStore Viewer: open tools/data_store/index.html")
    uvicorn.run(create_datastore_app(), host=args.host, port=args.port)
