import os
import asyncio
from fastapi import Depends, FastAPI
from app.routes import auth, documents
from app.services.queue_worker import background_worker

# Initialize FastAPI instance
app = FastAPI()

# Directories for uploads and DB
UPLOADS_DIR = "data/uploads"
DB_DIR = "data/db"
DB_PATH = os.path.join(DB_DIR, "app.db")

# Public auth routes.
app.include_router(auth.router, prefix="/auth", tags=["auth"])
# Protect all document endpoints with JWT bearer auth.
app.include_router(
    documents.router,
    dependencies=[Depends(auth.get_current_user)],
    tags=["documents"],
)

# FastAPI startup event
@app.on_event("startup")
async def startup():
    # Ensure directories exist
    os.makedirs(UPLOADS_DIR, exist_ok=True)  # Creates the uploads directory if it doesn't exist
    os.makedirs(DB_DIR, exist_ok=True)  # Creates the db directory if it doesn't exist

    # Start the background worker task
    asyncio.create_task(background_worker())  # Start the worker as a background task
    print("Background worker has started.")

# FastAPI shutdown event (optional)
@app.on_event("shutdown")
async def shutdown():
    print("Shutting down the application...")
    # Optionally stop background tasks or close resources if needed
