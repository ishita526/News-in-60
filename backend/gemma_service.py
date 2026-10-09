"""
Gemma summarization service.

Wraps the google-genai client and handles:
- Text summarization
- Image summarization
- One controlled retry if the summary exceeds 110 words
"""

import os
import time

from google import genai
from google.genai import types

from prompts import (
    IMAGE_PROMPT_TEMPLATE,
    SHORTEN_PROMPT_TEMPLATE,
    SYSTEM_INSTRUCTION,
    TEXT_PROMPT_TEMPLATE,
)

MODEL = os.getenv("GEMMA_MODEL", "gemma-4-26b-a4b-it")
FALLBACK_MODEL = "gemma-4-31b-it"
MAX_WORDS = 110
TARGET_MIN_WORDS = 90


def _build_client() -> genai.Client:
    api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GOOGLE_API_KEY is not set in the environment.")
    return genai.Client(api_key=api_key)


def _generate(client: genai.Client, contents) -> str:
    """
    Generate content using PRIMARY MODEL (gemma-4-31b-it), falling back to
    FALLBACK_MODEL (gemma-4-26b-a4b-it) if the primary model encounters
    temporary capacity spikes, 503 unavailable, or 500 server errors.
    """
    try:
        response = client.models.generate_content(
            model=MODEL,
            contents=contents,
        )
        if response and response.text:
            return response.text.strip()
    except Exception as exc:
        print(f"Notice: {MODEL} call failed ({exc}). Falling back to {FALLBACK_MODEL}...")

    try:
        response = client.models.generate_content(
            model=FALLBACK_MODEL,
            contents=contents,
        )
        if response and response.text:
            return response.text.strip()
    except Exception as exc:
        raise RuntimeError(f"Gemma fallback ({FALLBACK_MODEL}) also failed: {exc}")

    raise RuntimeError("Gemma response was empty.")


def _count_words(text: str) -> int:
    return len(text.split())


def _shorten_if_needed(client: genai.Client, summary: str) -> tuple[str, int]:
    """
    If the summary exceeds MAX_WORDS, make exactly one retry asking Gemma
    to shorten it. Returns (final_summary, word_count).
    """
    word_count = _count_words(summary)

    if word_count <= MAX_WORDS:
        return summary, word_count

    shorten_prompt = SHORTEN_PROMPT_TEMPLATE.format(
        word_count=word_count,
        summary=summary,
    )

    shortened = _generate(client, shorten_prompt)
    return shortened, _count_words(shortened)


def summarize_text(article_text: str) -> dict:
    """
    Summarize a news article provided as plain text.
    Returns {"summary": str, "word_count": int}.
    """
    client = _build_client()

    prompt = TEXT_PROMPT_TEMPLATE.format(
        system_instruction=SYSTEM_INSTRUCTION,
        article_text=article_text,
    )

    summary = _generate(client, prompt)
    summary, word_count = _shorten_if_needed(client, summary)

    return {"summary": summary, "word_count": word_count}


def summarize_image(image_bytes: bytes, mime_type: str) -> dict:
    """
    Summarize a news article provided as an image.
    Returns {"summary": str, "word_count": int}.
    """
    client = _build_client()

    image_part = types.Part.from_bytes(
        data=image_bytes,
        mime_type=mime_type,
    )

    prompt = IMAGE_PROMPT_TEMPLATE.format(
        system_instruction=SYSTEM_INSTRUCTION,
    )

    summary = _generate(client, [image_part, prompt])
    summary, word_count = _shorten_if_needed(client, summary)

    return {"summary": summary, "word_count": word_count}

