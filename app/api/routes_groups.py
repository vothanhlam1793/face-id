from __future__ import annotations

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import JSONResponse

from app.api.dependencies import service


router = APIRouter()


@router.post("/api/groups/create_person")
def create_person(group_id: str = Form(...), name: str = Form(...)) -> JSONResponse:
    service.create_person_from_group(group_id, name)
    return JSONResponse({"ok": True})


@router.post("/api/groups/attach_person")
def attach_person(group_id: str = Form(...), person_id: str = Form(...)) -> JSONResponse:
    service.attach_group_to_person(group_id, person_id)
    return JSONResponse({"ok": True})


@router.post("/api/groups/dismiss")
def dismiss(group_id: str = Form(...)) -> JSONResponse:
    service.dismiss_group(group_id)
    return JSONResponse({"ok": True})


@router.post("/api/groups/delete_sample")
def delete_sample(group_id: str = Form(...), sample_id: str = Form(...)) -> JSONResponse:
    service.delete_group_sample(group_id, sample_id)
    return JSONResponse({"ok": True})


@router.post("/api/groups/recheck")
def recheck_groups() -> JSONResponse:
    return JSONResponse(service.recheck_groups())


@router.post("/api/system/rebuild_embeddings")
def rebuild_embeddings() -> JSONResponse:
    return JSONResponse(service.rebuild_embeddings())


@router.post("/api/groups/import_images")
async def import_images(files: list[UploadFile] = File(...)) -> JSONResponse:
    payload: list[tuple[str, bytes]] = []
    for file in files:
        payload.append((file.filename or "image", await file.read()))
    return JSONResponse(service.import_images(payload))
