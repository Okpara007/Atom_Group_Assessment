from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from app.routes.auth import get_current_user
from app.services.persistence import (
    delete_document_and_related,
    get_document_analysis_result,
    get_document_by_id,
    get_recent_status_events,
    get_status_events_after_rowid,
    get_document_status_history,
    insert_document_metadata,
    list_documents as list_documents_db,
)
from app.services.queue_worker import (
    add_document_to_queue,
    document_queue,
    get_queue_snapshot,
    is_currently_processing,
    remove_document_from_queue,
)
import app.services.queue_worker as queue_worker
from sse_starlette import EventSourceResponse
import json
import os
import shutil
import uuid
from app.config import UPLOADS_DIR
import asyncio

router = APIRouter()
MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024
ALLOWED_EXTENSIONS = {".pdf", ".txt"}
ALLOWED_CONTENT_TYPES = {"application/pdf", "text/plain"}


def _safe_json(value):
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return value
    return value


@router.post("/upload")
async def upload_document(
    files: list[UploadFile] = File(...),
    current_user: str = Depends(get_current_user),
):
    if not files:
        raise HTTPException(status_code=400, detail="No files provided.")

    os.makedirs(UPLOADS_DIR, exist_ok=True)

    uploaded_documents = []
    errors = []

    for file in files:
        document_id = str(uuid.uuid4())
        filename = os.path.basename(file.filename or "")
        content_type = file.content_type

        try:
            if not filename:
                errors.append({"filename": file.filename, "error": "Filename is missing or invalid."})
                continue

            ext = os.path.splitext(filename)[1].lower()
            if ext not in ALLOWED_EXTENSIONS:
                errors.append(
                    {
                        "filename": filename,
                        "error": "Invalid file type. Only .pdf and .txt files are allowed.",
                    }
                )
                continue

            if content_type and content_type not in ALLOWED_CONTENT_TYPES:
                errors.append(
                    {
                        "filename": filename,
                        "error": "Invalid content type. Expected application/pdf or text/plain.",
                    }
                )
                continue

            file_bytes = await file.read()
            file_size = len(file_bytes)
            if file_size > MAX_FILE_SIZE_BYTES:
                errors.append(
                    {
                        "filename": filename,
                        "error": "File exceeds max size of 10MB.",
                    }
                )
                continue

            document_upload_dir = os.path.join(UPLOADS_DIR, document_id)
            os.makedirs(document_upload_dir, exist_ok=True)
            file_path = os.path.join(document_upload_dir, filename)

            with open(file_path, "wb") as f:
                f.write(file_bytes)

            insert_document_metadata(
                document_id,
                owner_username=current_user,
                original_filename=filename,
                stored_path=file_path,
                content_type=content_type,
                size_bytes=file_size,
                status="pending",
            )

            await add_document_to_queue(document_id)
            uploaded_documents.append(
                {
                    "document_id": document_id,
                    "filename": filename,
                    "size_bytes": file_size,
                    "content_type": content_type,
                    "status": "pending",
                    "stored_path": file_path,
                }
            )

        except Exception as e:
            errors.append({"filename": filename, "error": str(e)})

    if not uploaded_documents:
        raise HTTPException(
            status_code=400,
            detail={"message": "No valid files were uploaded.", "errors": errors},
        )

    return {
        "message": "Files processed.",
        "uploaded_count": len(uploaded_documents),
        "uploaded_documents": uploaded_documents,
        "failed_count": len(errors),
        "errors": errors,
    }


@router.get("/documents")
async def list_documents(
    status: str | None = Query(default=None),
    current_user: str = Depends(get_current_user),
):
    allowed_statuses = {"pending", "processing", "analyzing", "completed", "failed"}
    if status is not None and status not in allowed_statuses:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status filter. Allowed values: {sorted(allowed_statuses)}",
        )

    docs = list_documents_db(owner_username=current_user, status_filter=status)
    return {"documents": [dict(row) for row in docs]}


@router.get("/documents/stream")
async def stream_documents(
    request: Request,
    current_user: str = Depends(get_current_user),
):
    async def event_generator():
        last_rowid = 0

        try:
            recent_events = get_recent_status_events(limit=50, owner_username=current_user)
            for event in recent_events:
                last_rowid = int(event["row_num"])
                payload = {
                    "document_id": event["document_id"],
                    "status": event["status"],
                    "timestamp": event["timestamp"],
                    "metadata": _safe_json(event["metadata"]),
                    "error_message": event["error_message"],
                }

                if event["status"] == "completed":
                    analysis = get_document_analysis_result(
                        event["document_id"],
                        owner_username=current_user,
                    )
                    if analysis:
                        payload["result"] = {
                            "summary": analysis["summary"],
                            "key_topics": _safe_json(analysis["key_topics"]) or [],
                            "sentiment": analysis["sentiment"],
                            "actionable_items": _safe_json(analysis["actionable_items"]) or [],
                        }

                yield {
                    "event": "status",
                    "data": json.dumps(payload),
                }

            while True:
                if await request.is_disconnected():
                    print("SSE client disconnected, closing stream.")
                    break

                new_events = get_status_events_after_rowid(
                    last_rowid,
                    limit=200,
                    owner_username=current_user,
                )
                if not new_events:
                    yield {
                        "event": "heartbeat",
                        "data": json.dumps({"status": "idle", "message": "stream_alive"}),
                    }
                    await asyncio.sleep(1)
                    continue

                for event in new_events:
                    last_rowid = int(event["row_num"])
                    payload = {
                        "document_id": event["document_id"],
                        "status": event["status"],
                        "timestamp": event["timestamp"],
                        "metadata": _safe_json(event["metadata"]),
                        "error_message": event["error_message"],
                    }

                    if event["status"] == "completed":
                        analysis = get_document_analysis_result(
                            event["document_id"],
                            owner_username=current_user,
                        )
                        if analysis:
                            payload["result"] = {
                                "summary": analysis["summary"],
                                "key_topics": _safe_json(analysis["key_topics"]) or [],
                                "sentiment": analysis["sentiment"],
                                "actionable_items": _safe_json(analysis["actionable_items"]) or [],
                            }

                    yield {"event": "status", "data": json.dumps(payload)}
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            print("SSE stream cancelled by client.")
            raise
        finally:
            print("SSE stream cleanup complete.")

    return EventSourceResponse(event_generator())


@router.get("/documents/{id}")
async def get_document(id: str, current_user: str = Depends(get_current_user)):
    document = get_document_by_id(id, owner_username=current_user)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found.")

    status_history = get_document_status_history(id, owner_username=current_user)
    analysis = get_document_analysis_result(id, owner_username=current_user)

    return {
        "document": dict(document),
        "status_history": [dict(event) for event in status_history],
        "analysis_result": dict(analysis) if analysis else None,
    }


@router.get("/documents/{id}/status")
async def get_document_status(id: str, current_user: str = Depends(get_current_user)):
    document = get_document_by_id(id, owner_username=current_user)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found.")

    queued = id in get_queue_snapshot()
    processing = is_currently_processing(id)
    return {
        "document_id": id,
        "current_status": document["current_status"],
        "is_queued": queued,
        "is_processing": processing,
        "error_message": document["error_message"],
    }


@router.delete("/documents/{id}")
async def delete_document(id: str, current_user: str = Depends(get_current_user)):
    if is_currently_processing(id):
        raise HTTPException(
            status_code=409,
            detail="Document is currently processing and cannot be deleted right now.",
        )

    remove_document_from_queue(id)
    deleted = delete_document_and_related(id, owner_username=current_user)
    if not deleted:
        raise HTTPException(status_code=404, detail="Document not found.")

    stored_path = deleted["stored_path"]
    if stored_path and os.path.exists(stored_path):
        os.remove(stored_path)

    document_dir = os.path.join(UPLOADS_DIR, id)
    if os.path.isdir(document_dir):
        shutil.rmtree(document_dir, ignore_errors=True)

    return {"message": "Document and associated data removed.", "document_id": id}
