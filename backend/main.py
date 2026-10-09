"""
News Summarizer — FastAPI backend
POST /api/summarize
"""

import asyncio
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from gemma_service import summarize_image, summarize_text

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

# Load environment variables from the project root .env (prefer GOOGLE_API_KEY)
_root_env = os.path.join(os.path.dirname(__file__), "..", ".env")
load_dotenv(_root_env)
_backend_env = os.path.join(os.path.dirname(__file__), ".env")
if os.path.exists(_backend_env):
    load_dotenv(_backend_env, override=False)

# Image upload limits
ALLOWED_MIME_TYPES = {
    "image/jpeg": "image/jpeg",
    "image/jpg": "image/jpeg",
    "image/png": "image/png",
    "image/webp": "image/webp",
}
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
MAX_IMAGE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not os.getenv("GOOGLE_API_KEY") and not os.getenv("GEMINI_API_KEY"):
        raise RuntimeError("GOOGLE_API_KEY is not set. Please add it to your .env file.")
    yield


app = FastAPI(
    title="News Summarizer API",
    description="Summarize news articles from text or images using Gemma.",
    version="1.0.0",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# CORS — allow localhost origins for local frontend development
# ---------------------------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:5000",
        "http://localhost:5173",
        "http://localhost:5500",
        "http://localhost:8080",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5500",
        "http://127.0.0.1:8080",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _detect_mime_type(filename: str, content_type: str | None, image_bytes: bytes = b"") -> str | None:
    """
    Determine the MIME type from binary magic bytes or file extension.
    Falls back to the content_type header if extension is ambiguous.
    """
    if image_bytes.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if image_bytes.startswith(b"RIFF") and len(image_bytes) >= 12 and image_bytes[8:12] == b"WEBP":
        return "image/webp"

    ext = os.path.splitext(filename or "")[1].lower()
    if ext in ALLOWED_EXTENSIONS:
        return ALLOWED_MIME_TYPES.get(
            "image/jpeg" if ext in {".jpg", ".jpeg"} else f"image/{ext.lstrip('.')}"
        )
    if content_type and content_type in ALLOWED_MIME_TYPES:
        return ALLOWED_MIME_TYPES[content_type]
    return None


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@app.post("/api/summarize")
async def summarize(
    text: str | None = Form(default=None),
    image: UploadFile | None = File(default=None),
):
    """
    Summarize a news article from text or an uploaded image.

    - Send `text` (form field) for a text article.
    - Send `image` (form file) for a news image (JPG, JPEG, PNG, WEBP).
    - At least one of `text` or `image` must be provided.
    """

    # ------------------------------------------------------------------
    # 1. Validate that at least one input is present
    # ------------------------------------------------------------------
    has_text = text and text.strip()
    has_image = image is not None and image.filename

    if not has_text and not has_image:
        raise HTTPException(
            status_code=422,
            detail={"error": "No text or image was provided."},
        )

    # ------------------------------------------------------------------
    # 2. Image path
    # ------------------------------------------------------------------
    if has_image:
        # Read and size-check
        image_bytes = await image.read()
        if len(image_bytes) == 0:
            raise HTTPException(
                status_code=400,
                detail={"error": "The uploaded image file is empty (0 bytes)."},
            )
        if len(image_bytes) > MAX_IMAGE_SIZE_BYTES:
            raise HTTPException(
                status_code=413,
                detail={
                    "error": (
                        f"Image is too large ({len(image_bytes) // (1024 * 1024)} MB). "
                        f"Maximum allowed size is {MAX_IMAGE_SIZE_BYTES // (1024 * 1024)} MB."
                    )
                },
            )

        # Validate extension / MIME type (inspecting binary magic bytes)
        mime_type = _detect_mime_type(image.filename, image.content_type, image_bytes)
        if mime_type is None:
            raise HTTPException(
                status_code=415,
                detail={
                    "error": (
                        f"Unsupported image type '{image.filename}'. "
                        "Accepted formats: JPG, JPEG, PNG, WEBP."
                    )
                },
            )

        try:
            result = await asyncio.to_thread(summarize_image, image_bytes, mime_type)
        except RuntimeError as exc:
            err_str = str(exc)
            if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str or "quota" in err_str.lower():
                raise HTTPException(status_code=429, detail={"error": "AI service quota or rate limit exceeded. Please wait a moment and try again."})
            if "503" in err_str or "UNAVAILABLE" in err_str or "high demand" in err_str.lower():
                raise HTTPException(status_code=503, detail={"error": "The AI service is experiencing high demand. Please retry in a few moments."})
            raise HTTPException(status_code=500, detail={"error": err_str})
        except Exception as exc:
            err_str = str(exc)
            if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str or "quota" in err_str.lower():
                raise HTTPException(status_code=429, detail={"error": "AI service quota or rate limit exceeded. Please wait a moment and try again."})
            if "503" in err_str or "UNAVAILABLE" in err_str or "high demand" in err_str.lower():
                raise HTTPException(status_code=503, detail={"error": "The AI service is experiencing high demand. Please retry in a few moments."})
            raise HTTPException(
                status_code=502,
                detail={"error": f"Gemma API error: {exc}"},
            )

        return result

    # ------------------------------------------------------------------
    # 3. Text path
    # ------------------------------------------------------------------
    try:
        result = await asyncio.to_thread(summarize_text, text.strip())
    except RuntimeError as exc:
        err_str = str(exc)
        if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str or "quota" in err_str.lower():
            raise HTTPException(status_code=429, detail={"error": "AI service quota or rate limit exceeded. Please wait a moment and try again."})
        if "503" in err_str or "UNAVAILABLE" in err_str or "high demand" in err_str.lower():
            raise HTTPException(status_code=503, detail={"error": "The AI service is experiencing high demand. Please retry in a few moments."})
        raise HTTPException(status_code=500, detail={"error": err_str})
    except Exception as exc:
        err_str = str(exc)
        if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str or "quota" in err_str.lower():
            raise HTTPException(status_code=429, detail={"error": "AI service quota or rate limit exceeded. Please wait a moment and try again."})
        if "503" in err_str or "UNAVAILABLE" in err_str or "high demand" in err_str.lower():
            raise HTTPException(status_code=503, detail={"error": "The AI service is experiencing high demand. Please retry in a few moments."})
        raise HTTPException(
            status_code=502,
            detail={"error": f"Gemma API error: {exc}"},
        )

    return result


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


@app.get("/health")
async def health():
    return {"status": "ok"}
