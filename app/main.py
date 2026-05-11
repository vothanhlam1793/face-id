from __future__ import annotations

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.routes_groups import router as groups_router
from app.api.routes_pages import router as pages_router
from app.api.routes_state import router as state_router
from app.config import SNAPSHOT_DIR, STATIC_DIR


app = FastAPI(title="Face ID Local")
app.mount("/snapshots", StaticFiles(directory=SNAPSHOT_DIR), name="snapshots")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

app.include_router(pages_router)
app.include_router(state_router)
app.include_router(groups_router)
