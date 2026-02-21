import json
import re
import time

from openai import APIConnectionError, APIError, APITimeoutError, OpenAI, RateLimitError
from app.config import OPENAI_API_KEY


OPENAI_MODEL = "gpt-4.1"
MAX_TEXT_CHARS = 20000
_client = None


class LLMError(Exception):
    pass


def _build_prompt(document_text: str) -> str:
    trimmed_text = document_text[:MAX_TEXT_CHARS]
    return (
        "Analyze the document text and return ONLY valid JSON with this exact shape:\n"
        "{\n"
        '  "summary": "3-5 sentence concise summary",\n'
        '  "key_topics": ["topic1", "topic2"],\n'
        '  "sentiment": "positive|negative|neutral|mixed",\n'
        '  "actionable_items": ["item1", "item2"]\n'
        "}\n\n"
        "Rules:\n"
        "- summary must be 3-5 sentences.\n"
        "- key_topics and actionable_items must be arrays of strings.\n"
        "- sentiment must be exactly one of: positive, negative, neutral, mixed.\n"
        "- If no actionable items are present, return an empty array.\n\n"
        "Document text:\n"
        f"{trimmed_text}"
    )


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=OPENAI_API_KEY)
    return _client


def _count_sentences(text: str) -> int:
    parts = re.split(r"[.!?]+", text)
    return len([p for p in parts if p.strip()])


def _normalize_string_list(value) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _call_openai_chat_completions(prompt: str) -> dict:
    if not OPENAI_API_KEY:
        raise LLMError("OPENAI_API_KEY is not configured.")

    try:
        completion = _get_client().chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": "You are a precise document analysis assistant.",
                },
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
            timeout=45,
        )
    except (APITimeoutError, APIConnectionError, RateLimitError, APIError) as e:
        raise LLMError(f"OpenAI API error: {e}") from e
    except Exception as e:
        raise LLMError(f"OpenAI request failed: {e}") from e

    try:
        message_content = completion.choices[0].message.content
        if not message_content:
            raise ValueError("Empty completion content.")
        parsed = json.loads(message_content)
    except Exception as e:
        raise LLMError(f"Failed to parse OpenAI response: {e}") from e

    summary = str(parsed.get("summary", "")).strip()
    sentence_count = _count_sentences(summary)
    if sentence_count < 3 or sentence_count > 5:
        raise LLMError("LLM summary is not within 3-5 sentences.")

    sentiment = parsed.get("sentiment")
    if sentiment not in {"positive", "negative", "neutral", "mixed"}:
        raise LLMError("LLM returned invalid sentiment value.")

    result = {
        "summary": summary,
        "key_topics": _normalize_string_list(parsed.get("key_topics", [])),
        "sentiment": sentiment,
        "actionable_items": _normalize_string_list(parsed.get("actionable_items", [])),
        "raw_model_output": completion.model_dump(),
    }
    return result


def analyze_document_with_retry(document_text: str, max_retries: int = 1) -> dict:
    attempts = max_retries + 1
    last_error = None
    prompt = _build_prompt(document_text)

    for attempt in range(attempts):
        try:
            return _call_openai_chat_completions(prompt)
        except LLMError as e:
            last_error = e
            if attempt < attempts - 1:
                time.sleep(1)
            else:
                break

    raise LLMError(f"Analysis failed after retry: {last_error}")
