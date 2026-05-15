"""Common LLM wrapper with structured output via Pydantic.

Provider-agnostic: defaults to a local OpenAI-compatible 9router gateway,
falls back to public OpenAI when SPONSORUS_LLM_BASE_URL points elsewhere.
"""
from __future__ import annotations

import json
import os
from functools import lru_cache
from typing import Type, TypeVar

from openai import OpenAI
from pydantic import BaseModel
from tenacity import retry, stop_after_attempt, wait_exponential

T = TypeVar("T", bound=BaseModel)

DEFAULT_MODEL = os.environ.get("SPONSORUS_LLM_MODEL", "cx/gpt-5.5")
DEFAULT_BASE_URL = os.environ.get("SPONSORUS_LLM_BASE_URL", "http://localhost:20128/v1")
# 9router accepts any non-empty bearer; for hosted OpenAI set OPENAI_API_KEY.
DEFAULT_API_KEY = os.environ.get("OPENAI_API_KEY", "sk-9router-local")


@lru_cache(maxsize=1)
def client() -> OpenAI:
    return OpenAI(base_url=DEFAULT_BASE_URL, api_key=DEFAULT_API_KEY)


def _supports_response_format() -> bool:
    """9router doesn't always honor response_format=json_object; toggle via env."""
    return os.environ.get("SPONSORUS_JSON_MODE", "false").lower() in ("1", "true", "yes")


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
def structured(
    *,
    system: str,
    user: str,
    schema: Type[T],
    model: str = DEFAULT_MODEL,
    temperature: float = 0.2,
) -> T:
    """Call the LLM and parse the response into a Pydantic model.

    Strategy: include the schema in the system prompt and ask for raw JSON.
    Some gateways (incl. 9router) do not support response_format=json_object,
    so we extract the first JSON object from the response defensively.
    """
    schema_json = json.dumps(schema.model_json_schema(), indent=2)
    sys_full = (
        f"{system}\n\n"
        f"You MUST respond with a single JSON object matching this exact schema:\n"
        f"```json\n{schema_json}\n```\n"
        "Output raw JSON only. Do not wrap it in markdown fences. No commentary before or after."
    )
    kwargs: dict = dict(
        model=model,
        messages=[
            {"role": "system", "content": sys_full},
            {"role": "user", "content": user},
        ],
        temperature=temperature,
    )
    if _supports_response_format():
        kwargs["response_format"] = {"type": "json_object"}
    resp = client().chat.completions.create(**kwargs)
    content = (resp.choices[0].message.content or "").strip()
    if not content:
        raise ValueError("empty LLM response")
    # Defensive JSON extraction: strip ``` fences and pick the first {...} block.
    if content.startswith("```"):
        content = content.strip("`")
        if content.lower().startswith("json"):
            content = content[4:].lstrip()
    if not content.startswith("{"):
        start = content.find("{")
        end = content.rfind("}")
        if start >= 0 and end > start:
            content = content[start : end + 1]
    return schema.model_validate_json(content)


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
def freeform(
    *,
    system: str,
    user: str,
    model: str = DEFAULT_MODEL,
    temperature: float = 0.4,
) -> str:
    resp = client().chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=temperature,
    )
    return resp.choices[0].message.content or ""
