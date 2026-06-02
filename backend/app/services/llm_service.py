"""LLM service — Ollama integration for screenshot analysis.

Sends images to the Ollama ``/api/chat`` endpoint with a structured prompt
that requests JSON output. Handles retries, timeouts, and response parsing.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

import httpx
import structlog

from app.services.image_service import encode_base64

logger = structlog.get_logger()

# ── Prompt ──────────────────────────────────────────────────────────

ANALYSIS_PROMPT_V1 = """You are an image analysis assistant. Analyze the screenshot provided and respond with ONLY a JSON object (no markdown, no explanation, no code fences). The JSON must follow this exact schema:

{
  "description": "A 2-3 sentence description of what is shown in the image",
  "tags": ["tag1", "tag2", "tag3"],
  "category": "document|social|receipt|code|map|photo|meme|other",
  "contains_text": true,
  "extracted_text": "Any visible text in the image, or null if none",
  "language": "pt|en|es|fr|de|other"
}

Rules:
- Tags must be lowercase single words or hyphenated phrases (max 6 tags)
- Category must be exactly one of the allowed values
- Be concise and accurate
- Respond with ONLY the JSON object"""

PROMPT_VERSION = "v1"


@dataclass
class AnalysisResult:
    """Parsed result from LLM analysis."""

    description: str
    tags: list[str]
    category: str
    contains_text: bool
    extracted_text: str | None
    language: str | None
    model_used: str
    prompt_version: str = PROMPT_VERSION


# ── Valid categories ────────────────────────────────────────────────

VALID_CATEGORIES = frozenset({
    "document", "social", "receipt", "code", "map", "photo", "meme", "other"
})


def _sanitize_json_response(text: str) -> str:
    """Strip markdown fencing and extra whitespace from LLM response."""
    # Remove ```json ... ``` or ``` ... ``` wrappers
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*\n?", "", text)
    text = re.sub(r"\n?```\s*$", "", text)
    return text.strip()


def _parse_response(raw: str) -> dict:
    """Parse and validate the JSON response from the LLM.

    Raises:
        ValueError: If the response cannot be parsed or is invalid.
    """
    cleaned = _sanitize_json_response(raw)

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise ValueError(f"LLM returned invalid JSON: {e}\nRaw: {cleaned[:200]}") from e

    # Validate required fields
    required = {"description", "tags", "category", "contains_text"}
    missing = required - set(data.keys())
    if missing:
        raise ValueError(f"LLM response missing fields: {missing}")

    # Normalise category
    category = str(data["category"]).lower().strip()
    if category not in VALID_CATEGORIES:
        category = "other"
    data["category"] = category

    # Ensure tags is a list of strings
    if not isinstance(data["tags"], list):
        data["tags"] = [str(data["tags"])]
    data["tags"] = [str(t).lower().strip() for t in data["tags"]][:6]

    return data


class LLMService:
    """Ollama-backed image analysis service."""

    def __init__(self, base_url: str, model: str):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=httpx.Timeout(180.0, connect=10.0))
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def check_connection(self) -> bool:
        """Check if Ollama is reachable and the model is available."""
        try:
            client = await self._get_client()
            resp = await client.get(f"{self.base_url}/api/tags", timeout=5.0)
            if resp.status_code != 200:
                return False
            data = resp.json()
            models = [m.get("name", "") for m in data.get("models", [])]
            # Check if our model (with or without tag) is available
            return any(self.model in m for m in models)
        except Exception as e:
            logger.warning("llm.connection_failed", error=str(e))
            return False

    async def analyze_image(self, file_path: str) -> AnalysisResult:
        """Analyze a screenshot and return structured analysis.

        Retries up to 3 times with exponential backoff (2s, 4s, 8s).

        Raises:
            RuntimeError: If analysis fails after all retries.
        """
        image_b64 = encode_base64(file_path, max_size=1280)
        client = await self._get_client()

        last_error: Exception | None = None
        backoff_delays = [2, 4, 8]

        for attempt in range(3):
            try:
                logger.info(
                    "llm.analyze_start",
                    file=file_path,
                    model=self.model,
                    attempt=attempt + 1,
                )

                payload = {
                    "model": self.model,
                    "messages": [
                        {
                            "role": "user",
                            "content": ANALYSIS_PROMPT_V1,
                            "images": [image_b64],
                        }
                    ],
                    "stream": False,
                }

                resp = await client.post(
                    f"{self.base_url}/api/chat",
                    json=payload,
                )
                resp.raise_for_status()

                result_data = resp.json()
                raw_content = result_data.get("message", {}).get("content", "")

                if not raw_content:
                    raise ValueError("Empty response from LLM")

                parsed = _parse_response(raw_content)

                logger.info(
                    "llm.analyze_complete",
                    file=file_path,
                    category=parsed["category"],
                    tags=parsed["tags"],
                )

                return AnalysisResult(
                    description=parsed["description"],
                    tags=parsed["tags"],
                    category=parsed["category"],
                    contains_text=bool(parsed.get("contains_text", False)),
                    extracted_text=parsed.get("extracted_text"),
                    language=parsed.get("language"),
                    model_used=self.model,
                    prompt_version=PROMPT_VERSION,
                )

            except Exception as e:
                last_error = e
                logger.warning(
                    "llm.analyze_retry",
                    file=file_path,
                    attempt=attempt + 1,
                    error=str(e),
                )
                if attempt < len(backoff_delays):
                    import asyncio
                    await asyncio.sleep(backoff_delays[attempt])

        raise RuntimeError(
            f"LLM analysis failed after 3 attempts: {last_error}"
        ) from last_error
