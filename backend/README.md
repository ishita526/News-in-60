# News Summarizer — Backend

A FastAPI backend that uses **Gemma** (via Google AI Studio) to summarize news articles from either plain text or uploaded images.

---

## Setup

### 1. Create / activate the virtual environment

```bash
python -m venv venv
# Windows
venv\Scripts\activate
# macOS / Linux
source venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure your API key

Edit `backend/.env` and add your Google AI Studio key:

```
GEMINI_API_KEY=your_actual_key_here
```

> The backend also checks the project-root `.env` as a fallback.

---

## Running the backend

From inside the `backend/` directory:

```bash
uvicorn main:app --reload
```

The API will be available at `http://127.0.0.1:8000`.

Interactive docs: `http://127.0.0.1:8000/docs`

---

## Endpoint

### `POST /api/summarize`

Accepts **multipart/form-data** with either or both of:

| Field  | Type        | Description                              |
|--------|-------------|------------------------------------------|
| `text` | string      | Plain-text news article                  |
| `image`| file upload | News image (JPG, JPEG, PNG, WEBP, ≤ 10 MB) |

At least one field must be present.

#### Success response

```json
{
  "summary": "A short, plain-English summary of the news article.",
  "word_count": 97
}
```

#### Error responses

```json
{ "error": "No text or image was provided." }
{ "error": "Unsupported image type 'file.gif'. Accepted formats: JPG, JPEG, PNG, WEBP." }
{ "error": "Image is too large (15 MB). Maximum allowed size is 10 MB." }
{ "error": "Gemma API error: ..." }
```

---

## Testing with curl

**Text input:**
```bash
curl -X POST http://127.0.0.1:8000/api/summarize \
  -F "text=Paste your news article text here."
```

**Image input:**
```bash
curl -X POST http://127.0.0.1:8000/api/summarize \
  -F "image=@/path/to/news.jpg"
```

**Missing input (expect 422):**
```bash
curl -X POST http://127.0.0.1:8000/api/summarize
```

**Invalid image type (expect 415):**
```bash
curl -X POST http://127.0.0.1:8000/api/summarize \
  -F "image=@/path/to/file.gif"
```

---

## Health check

```bash
curl http://127.0.0.1:8000/health
# {"status":"ok"}
```
