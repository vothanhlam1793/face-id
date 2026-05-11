from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from fastapi.responses import JSONResponse, Response, StreamingResponse

from app.api.dependencies import service


router = APIRouter()


class CameraConfigPayload(BaseModel):
    source_type: str
    source_value: str


@router.get("/api/state")
def api_state() -> JSONResponse:
    return JSONResponse(service.get_state())


@router.get("/api/camera/devices")
def api_camera_devices() -> JSONResponse:
    return JSONResponse(service.get_camera_devices())


@router.post("/api/camera/configure")
def api_configure_camera(payload: CameraConfigPayload) -> JSONResponse:
    return JSONResponse(service.configure_camera(payload.source_type, payload.source_value))


@router.post("/api/camera/start")
def api_start_camera() -> JSONResponse:
    return JSONResponse(service.start_camera())


@router.post("/api/camera/stop")
def api_stop_camera() -> JSONResponse:
    return JSONResponse(service.stop_camera())


@router.get("/api/review_state")
def api_review_state() -> JSONResponse:
    return JSONResponse(service.get_review_state())


@router.get("/video_feed")
def video_feed() -> StreamingResponse:
    return StreamingResponse(service.mjpeg_stream(), media_type="multipart/x-mixed-replace; boundary=frame")


@router.get("/media/{storage_path:path}")
def media_file(storage_path: str) -> Response:
    content = service.storage.read_bytes(storage_path)
    if content is None:
        raise HTTPException(status_code=404, detail="Media not found")
    suffix = Path(storage_path).suffix.lower()
    media_type = "image/jpeg"
    if suffix == ".png":
        media_type = "image/png"
    return Response(content=content, media_type=media_type)
