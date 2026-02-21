import os

from pdfminer.high_level import extract_text as extract_pdf_text


class ExtractionError(Exception):
    pass


def extract_text_from_document(stored_path: str, content_type: str | None = None) -> str:
    if not stored_path or not os.path.exists(stored_path):
        raise ExtractionError("Stored file path is missing or file does not exist.")

    ext = os.path.splitext(stored_path)[1].lower()
    is_txt = ext == ".txt" or content_type == "text/plain"
    is_pdf = ext == ".pdf" or content_type == "application/pdf"

    try:
        if is_txt:
            with open(stored_path, "r", encoding="utf-8", errors="replace") as f:
                text = f.read()
        elif is_pdf:
            text = extract_pdf_text(stored_path)
        else:
            raise ExtractionError("Unsupported document type for extraction.")
    except Exception as e:
        raise ExtractionError(f"Failed to extract text: {e}") from e

    normalized = (text or "").strip()
    if not normalized:
        raise ExtractionError("No readable text found in document.")
    return normalized
