# ATOM Group Backend AI Assessment

This project was built with FastAPI, SQLite, asyncio queue workers, SSE streaming, JWT auth, and OpenAI (`gpt-4.1`) analysis.

## Features

- Multi-file upload (`.pdf`, `.txt`) with validation
- Per-file max size enforcement (10MB)
- Persistent metadata, status history, and analysis results in SQLite
- FIFO background processing queue using `asyncio.Queue`
- Real-time status streaming via SSE
- JWT authentication for all protected endpoints
- AI-powered analysis with OpenAI SDK (`openai`) and retry-once error handling
- Basic but meaningful API tests

## Project Structure

```text
atom_assessment/
├── app/
│   ├── main.py
│   ├── config.py
│   ├── routes/
│   │   ├── auth.py
│   │   └── documents.py
│   ├── services/
│   │   ├── persistence.py
│   │   ├── queue_worker.py
│   │   ├── extractor.py
│   │   ├── llm.py
│   │   ├── storage.py
│   │   └── streaming.py
│   └── models/
│       ├── schemas.py
│       └── domain.py
├── data/
│   ├── uploads/
│   └── db/
├── tests/
│   └── test_api.py
├── requirements.txt
└── README.md
```

## Setup

1. Create virtual environment:
```bash
python -m venv ./venv
```

2. Activate venv:
```bash
source venv/bin/activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Create `.env` from template:
```bash
cp .env.example .env
```

5. Set values in `.env`:
```env
JWT_SECRET_KEY=your_secure_jwt_secret
JWT_EXPIRY=60
OPENAI_API_KEY=your_openai_key
```

## Run

```bash
uvicorn app.main:app --reload
```

Open API docs:

`http://127.0.0.1:8000/docs`

## Authentication

- Public endpoint:
  - `POST /auth/login`
- Protected endpoints:
  - All `/upload`, `/documents*` routes require `Authorization: Bearer <token>`

Login payload:

```json
{
  "username": "user1",
  "password": "password123"
}
```

## Endpoint Summary

- `POST /upload`
  - Upload one or more files
  - Accepts only `.pdf` and `.txt`
  - Max 10MB per file
  - Stores file as `data/uploads/{document_id}/{filename}`
  - Returns uploaded items + per-file validation errors

- `GET /documents`
  - Lists documents for authenticated user
  - Supports optional query filter:
  - `GET /documents?status=pending|processing|analyzing|completed|failed`

- `GET /documents/{id}`
  - Returns:
  - Document metadata
  - Status history
  - Analysis result

- `GET /documents/{id}/status`
  - Returns current status and queue flags

- `GET /documents/stream`
  - SSE stream for real-time updates
  - Emits user-scoped status events
  - Emits heartbeat while idle
  - Includes `result` in `completed` event when analysis exists

- `DELETE /documents/{id}`
  - Deletes document and associated status/analysis records
  - Removes stored file + upload directory

## Architecture Overview

### Upload + Queue Flow

1. Client uploads file(s) to `POST /upload`.
2. File is validated and stored on disk.
3. Metadata is persisted in SQLite with initial `pending` status.
4. Document ID is pushed into `asyncio.Queue`.
5. Background worker consumes documents FIFO.

### Worker Pipeline

1. `processing`:
   - Worker loads document metadata
   - Extracts text (`pdfminer` for PDF, file read for TXT)
2. `analyzing`:
   - Worker sends extracted text to OpenAI (`gpt-4.1`) via official SDK
3. `completed`:
   - Stores summary/topics/sentiment/actionable items
4. `failed`:
   - On extraction/LLM errors, status is set to failed with reason

### Streaming

- SSE endpoint polls persisted `status_events`
- Streams status transitions in near real time
- Includes metadata, timestamp, and analysis result on completion
- Handles client disconnect with generator cleanup

## Design Decisions

- Queue:
  - `asyncio.Queue` chosen for simple in-process FIFO behavior
  - Trade-off: queue state itself is in-memory and not distributed

- Persistence:
  - SQLite chosen for lightweight durable storage without separate DB server
  - Status history stored as append-only events table

- Streaming:
  - SSE chosen for one-way server push with low complexity
  - Simple for browser and `curl -N` clients

- LLM Integration:
  - Official OpenAI Python SDK
  - Prompt enforces JSON schema-like output
  - Retry once on API failures before marking failed

## Testing

Run tests:

```bash
python -m unittest discover -s tests -p "test_*.py" -q
```

Current test coverage focus:

- Auth success/failure + protected route access
- Upload validation and storage path structure
- Status-filter listing behavior

## Time Breakdown (5 Hours)

- Project scaffolding and API structure: 45 min
- Auth and protected routing: 45 min
- Upload validation + persistence + queue wiring: 75 min
- Worker pipeline + extraction + LLM integration: 75 min
- SSE streaming and event shaping: 45 min
- Testing, cleanup, and docs: 35 min

## Trade-offs and Production Improvements

- Replace in-process queue with durable worker system (Redis/Celery or brokered queue) for horizontal scale.
- Add DB migrations (Alembic) instead of lightweight runtime schema updates.
- Add structured logging and tracing.
- Add rate limiting and abuse protection.
- Add chunked upload support for very large files.
- Add websocket option in addition to SSE if bi-directional control is needed.
- Add stronger test suite with integration and failure-mode cases.

## Notes

- Keep `.env` local and never commit secrets.
- `.env.example` is intentionally sanitized.
