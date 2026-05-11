from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import HTMLResponse
from fastapi.responses import Response

from app.config import TEMPLATES_DIR


router = APIRouter()


def _read_template(name: str) -> str:
    return (TEMPLATES_DIR / name).read_text(encoding="utf-8")


@router.get("/", response_class=HTMLResponse)
def index() -> str:
    return _read_template("index.html")


@router.get("/review", response_class=HTMLResponse)
def review() -> str:
    return _read_template("review.html")


@router.get("/.well-known/appspecific/com.chrome.devtools.json")
def chrome_devtools_hint() -> Response:
    return Response(status_code=204)
