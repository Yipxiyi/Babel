"""Translation provider adapters for Babel jobs."""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from xml.etree import ElementTree as ET

from .pipeline import element_to_snippet, parse_snippet


Transport = Callable[[str, dict[str, str], dict[str, Any]], dict[str, Any]]


@dataclass(frozen=True)
class ProviderSettings:
    provider: str
    model: str
    target_language: str
    base_url: str = ""
    api_key: str = ""
    temperature: float = 0.2


class TranslationProvider(ABC):
    @abstractmethod
    def translate_batch(self, rows: list[dict], glossary: str, context: str) -> list[dict]:
        """Translate source batch rows into `id` + `translated_html` rows."""


def default_transport(url: str, headers: dict[str, str], payload: dict[str, Any]) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"provider HTTP {exc.code}: {detail}") from exc


def strip_markdown_fence(text: str) -> str:
    value = text.strip()
    match = re.fullmatch(r"```(?:json|jsonl)?\s*(.*?)\s*```", value, flags=re.DOTALL)
    return match.group(1).strip() if match else value


def parse_translated_rows(text: str) -> list[dict]:
    value = strip_markdown_fence(text)
    if not value:
        return []
    try:
        parsed = json.loads(value)
        if isinstance(parsed, list):
            return [row for row in parsed if isinstance(row, dict)]
        if isinstance(parsed, dict) and isinstance(parsed.get("rows"), list):
            return [row for row in parsed["rows"] if isinstance(row, dict)]
    except json.JSONDecodeError:
        pass

    rows: list[dict] = []
    for line_number, line in enumerate(value.splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"provider returned invalid JSONL at line {line_number}: {exc}") from exc
        if not isinstance(row, dict):
            raise ValueError(f"provider returned non-object JSONL row at line {line_number}")
        rows.append(row)
    return rows


def batch_prompt(rows: list[dict], glossary: str, context: str, target_language: str) -> list[dict[str, str]]:
    compact_rows = [
        {
            "id": row["id"],
            "source_text": row.get("source_text", ""),
            "source_html": row.get("source_html", ""),
        }
        for row in rows
    ]
    system = (
        "You translate EPUB XHTML snippets while preserving structure. "
        f"Target language: {target_language}. "
        "Return only JSONL rows with exactly `id` and `translated_html`. "
        "Do not add markdown, commentary, summaries, or placeholder text. "
        "Preserve root tags, attributes, IDs, anchors, links, images, CSS classes, "
        "and inline emphasis tags. Translate only human-readable text."
    )
    user = (
        "# Glossary\n"
        f"{glossary.strip()}\n\n"
        "# Context\n"
        f"{context.strip()}\n\n"
        "# Batch Rows\n"
        f"{json.dumps(compact_rows, ensure_ascii=False)}"
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


class OpenAICompatibleProvider(TranslationProvider):
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        target_language: str,
        temperature: float = 0.2,
        transport: Transport = default_transport,
    ) -> None:
        if not base_url:
            raise ValueError("base_url is required for OpenAI-compatible providers")
        if not model:
            raise ValueError("model is required")
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.target_language = target_language
        self.temperature = temperature
        self.transport = transport

    def translate_batch(self, rows: list[dict], glossary: str, context: str) -> list[dict]:
        endpoint = self.base_url
        if not endpoint.endswith("/chat/completions"):
            endpoint = f"{endpoint}/chat/completions"
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        payload = {
            "model": self.model,
            "messages": batch_prompt(rows, glossary, context, self.target_language),
            "temperature": self.temperature,
        }
        response = self.transport(endpoint, headers, payload)
        try:
            content = response["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ValueError(f"unexpected OpenAI-compatible response: {response!r}") from exc
        return parse_translated_rows(content)


class AnthropicProvider(TranslationProvider):
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        target_language: str,
        base_url: str = "https://api.anthropic.com/v1",
        temperature: float = 0.2,
        transport: Transport = default_transport,
    ) -> None:
        if not api_key:
            raise ValueError("api_key is required for Anthropic")
        if not model:
            raise ValueError("model is required")
        self.api_key = api_key
        self.model = model
        self.target_language = target_language
        self.base_url = base_url.rstrip("/")
        self.temperature = temperature
        self.transport = transport

    def translate_batch(self, rows: list[dict], glossary: str, context: str) -> list[dict]:
        messages = batch_prompt(rows, glossary, context, self.target_language)
        system = messages[0]["content"]
        user = messages[1]["content"]
        response = self.transport(
            f"{self.base_url}/messages",
            {
                "Content-Type": "application/json",
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
            },
            {
                "model": self.model,
                "system": system,
                "messages": [{"role": "user", "content": user}],
                "max_tokens": 8192,
                "temperature": self.temperature,
            },
        )
        try:
            content_items = response["content"]
            content = "".join(item.get("text", "") for item in content_items if item.get("type") == "text")
        except (KeyError, TypeError) as exc:
            raise ValueError(f"unexpected Anthropic response: {response!r}") from exc
        return parse_translated_rows(content)


def _set_all_text(element: ET.Element) -> None:
    element.text = "测试翻译"
    for child in list(element):
        _set_all_text(child)
        child.tail = ""


class FakeProvider(TranslationProvider):
    """Deterministic local provider for tests and dry runs."""

    def translate_batch(self, rows: list[dict], glossary: str, context: str) -> list[dict]:
        translated: list[dict] = []
        for row in rows:
            element = parse_snippet(row["source_html"])
            _set_all_text(element)
            translated.append({"id": row["id"], "translated_html": element_to_snippet(element)})
        return translated


def make_provider(settings: ProviderSettings) -> TranslationProvider:
    provider = settings.provider.lower().strip()
    if provider in {"fake", "dry-run", "dry_run"}:
        return FakeProvider()
    if provider in {"openai", "openai-compatible", "openai_compatible", "compatible"}:
        return OpenAICompatibleProvider(
            base_url=settings.base_url,
            api_key=settings.api_key,
            model=settings.model,
            target_language=settings.target_language,
            temperature=settings.temperature,
        )
    if provider in {"anthropic", "claude"}:
        return AnthropicProvider(
            base_url=settings.base_url or "https://api.anthropic.com/v1",
            api_key=settings.api_key,
            model=settings.model,
            target_language=settings.target_language,
            temperature=settings.temperature,
        )
    raise ValueError(f"unsupported provider: {settings.provider}")
