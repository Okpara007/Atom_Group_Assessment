import os
import asyncio
from fastapi import Depends, FastAPI
from app.routes import auth, documents
from app.services.queue_worker import background_worker

app = FastAPI()

UPLOADS_DIR = "data/uploads"
DB_DIR = "data/db"
DB_PATH = os.path.join(DB_DIR, "app.db")

app.include_router(auth.router, prefix="/auth", tags=["auth"])

app.include_router(
    documents.router,
    dependencies=[Depends(auth.get_current_user)],
    tags=["documents"],
)

@app.on_event("startup")
async def startup():

    os.makedirs(UPLOADS_DIR, exist_ok=True)  
    os.makedirs(DB_DIR, exist_ok=True) 

    asyncio.create_task(background_worker()) 
    print("Background worker has started.")

@app.on_event("shutdown")
async def shutdown():
    print("Shutting down the application...")

