import asyncio
import json

from app.services.extractor import ExtractionError, extract_text_from_document
from app.services.llm import LLMError, analyze_document_with_retry
from app.services.persistence import get_document_by_id, insert_analysis_result, insert_status_event

# The queue for documents waiting to be processed
document_queue = asyncio.Queue()
current_document_id = None

# Background worker function that continuously processes documents from the queue
async def background_worker():
    global current_document_id
    while True:
        # Get the next document from the queue (this is a blocking operation)
        document_id = await document_queue.get()
        current_document_id = document_id

        try:
            # Log queue state.
            print(f"Queue Contents: {list(document_queue._queue)}")

            # Fetch document metadata from the database.
            document = get_document_by_id(document_id)
            if not document:
                raise RuntimeError("Document metadata not found in database.")

            # pending -> processing
            insert_status_event(
                document_id,
                status="processing",
                metadata='{"info": "Text extraction started."}',
            )

            print(f"Processing document {document_id}...")

            extracted_text = extract_text_from_document(
                stored_path=document["stored_path"],
                content_type=document["content_type"],
            )

            # processing -> analyzing
            insert_status_event(
                document_id,
                status="analyzing",
                metadata='{"info": "LLM analysis started."}',
            )

            analysis = analyze_document_with_retry(extracted_text, max_retries=1)
            insert_analysis_result(
                document_id=document_id,
                summary=analysis["summary"],
                key_topics=json.dumps(analysis["key_topics"]),
                sentiment=analysis["sentiment"],
                actionable_items=json.dumps(analysis["actionable_items"]),
                raw_model_output=json.dumps(analysis["raw_model_output"]),
            )

            # analyzing -> completed
            insert_status_event(
                document_id,
                status="completed",
                metadata='{"info": "Processing completed."}',
            )
            print(f"Document {document_id} processed successfully.")

        except (ExtractionError, LLMError, Exception) as e:
            print(f"Error processing document {document_id}: {e}")
            insert_status_event(
                document_id,
                status="failed",
                metadata='{"info": "Processing failed."}',
                error_message=str(e),
            )
        finally:
            # Mark the task as done even on error and clear active marker.
            document_queue.task_done()
            current_document_id = None

# Function to add a document to the queue for processing
async def add_document_to_queue(document_id: str):
    await document_queue.put(document_id)
    print(f"Document {document_id} added to queue.")
    print(f"Queue contents: {list(document_queue._queue)}")  # Log the current state of the queue


def get_queue_snapshot():
    return list(document_queue._queue)


def is_currently_processing(document_id: str) -> bool:
    return current_document_id == document_id


def remove_document_from_queue(document_id: str) -> bool:
    q = document_queue._queue
    try:
        q.remove(document_id)
        return True
    except ValueError:
        return False
