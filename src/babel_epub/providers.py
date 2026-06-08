"""Translation provider adapters for Babel jobs."""

from __future__ import annotations

import json
import re
import socket
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from xml.etree import ElementTree as ET

from .pipeline import element_to_snippet, local_name, parse_snippet, structural_tokens


Transport = Callable[..., dict[str, Any]]
DEFAULT_REQUEST_TIMEOUT = 300.0
DEFAULT_MAX_RETRIES = 2
DEFAULT_MAX_CONCURRENCY = 3
MAX_CONCURRENCY_LIMIT = 8


@dataclass(frozen=True)
class ProviderSettings:
    provider: str
    model: str
    target_language: str
    base_url: str = ""
    api_key: str = ""
    temperature: float = 0.2
    request_timeout: float = DEFAULT_REQUEST_TIMEOUT
    max_retries: int = DEFAULT_MAX_RETRIES
    max_concurrency: int = DEFAULT_MAX_CONCURRENCY


class TranslationProvider(ABC):
    @abstractmethod
    def translate_batch(self, rows: list[dict], glossary: str, context: str) -> list[dict]:
        """Translate source batch rows into `id` + `translated_html` rows."""

    def usage_snapshot(self) -> dict[str, int]:
        return dict(getattr(self, "_usage_summary", {}))

    def _record_response_usage(self, response: dict[str, Any]) -> None:
        usage = response.get("usage") if isinstance(response, dict) else None
        current = dict(getattr(self, "_usage_summary", {}))
        current["requests"] = int(current.get("requests", 0)) + 1
        if isinstance(usage, dict):
            prompt_tokens = _usage_int(usage, "prompt_tokens", "input_tokens")
            completion_tokens = _usage_int(usage, "completion_tokens", "output_tokens")
            total_tokens = _usage_int(usage, "total_tokens")
            if total_tokens == 0 and (prompt_tokens or completion_tokens):
                total_tokens = prompt_tokens + completion_tokens
            current["prompt_tokens"] = int(current.get("prompt_tokens", 0)) + prompt_tokens
            current["completion_tokens"] = int(current.get("completion_tokens", 0)) + completion_tokens
            current["total_tokens"] = int(current.get("total_tokens", 0)) + total_tokens
        self._usage_summary = current


def _usage_int(usage: dict[str, Any], *keys: str) -> int:
    for key in keys:
        value = usage.get(key)
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            return max(0, int(value))
    return 0


def default_transport(
    url: str,
    headers: dict[str, str],
    payload: dict[str, Any],
    timeout: float = DEFAULT_REQUEST_TIMEOUT,
) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"provider HTTP {exc.code}: {detail}") from exc
    except (TimeoutError, socket.timeout) as exc:
        raise TimeoutError(f"provider read timed out after {timeout:g}s") from exc
    except urllib.error.URLError as exc:
        if isinstance(exc.reason, (TimeoutError, socket.timeout)):
            raise TimeoutError(f"provider read timed out after {timeout:g}s") from exc
        raise


def normalize_max_concurrency(value: int | float | str | None) -> int:
    try:
        parsed = int(value) if value is not None else DEFAULT_MAX_CONCURRENCY
    except (TypeError, ValueError):
        parsed = DEFAULT_MAX_CONCURRENCY
    return min(max(parsed, 1), MAX_CONCURRENCY_LIMIT)


def normalize_max_retries(value: int | float | str | None) -> int:
    try:
        parsed = int(value) if value is not None else DEFAULT_MAX_RETRIES
    except (TypeError, ValueError):
        parsed = DEFAULT_MAX_RETRIES
    return min(max(parsed, 0), 5)


def normalize_request_timeout(value: int | float | str | None) -> float:
    try:
        parsed = float(value) if value is not None else DEFAULT_REQUEST_TIMEOUT
    except (TypeError, ValueError):
        parsed = DEFAULT_REQUEST_TIMEOUT
    return min(max(parsed, 30.0), 1800.0)


def is_retryable_provider_error(error: Exception) -> bool:
    if isinstance(error, TimeoutError):
        return True
    message = str(error).lower()
    if "timed out" in message or "timeout" in message:
        return True
    match = re.search(r"provider http\s+(\d{3})", message)
    if not match:
        return False
    status = int(match.group(1))
    return status == 429 or 500 <= status <= 599


def is_retryable_translation_output_error(error: Exception) -> bool:
    message = str(error).lower()
    retryable_fragments = (
        "provider returned invalid jsonl",
        "has validation issues",
        "missing translated row",
        "structural id/href/src tokens changed",
        "invalid translated_html xml snippet",
    )
    return isinstance(error, ValueError) and any(fragment in message for fragment in retryable_fragments)


def is_provider_safety_rejection(error: Exception) -> bool:
    message = str(error).lower()
    return (
        isinstance(error, ValueError)
        and "provider returned invalid jsonl" in message
        and (
            "considered high risk" in message
            or "request was rejected" in message
            or "safety" in message
        )
    )


def is_retryable_translation_error(error: Exception) -> bool:
    return is_retryable_provider_error(error) or is_retryable_translation_output_error(error)


def _is_official_openai_base_url(base_url: str) -> bool:
    value = base_url.lower().strip()
    return "api.openai.com" in value


def validate_provider_settings(settings: ProviderSettings) -> ProviderSettings:
    provider = settings.provider.lower().strip()
    model = settings.model.strip()
    base_url = settings.base_url.strip()
    api_key = settings.api_key.strip()
    if provider in {"fake", "dry-run", "dry_run"}:
        return settings
    if not model:
        raise ValueError("model is required")
    if provider in {"openai", "openai-compatible", "openai_compatible", "compatible"}:
        if not base_url:
            raise ValueError("base_url is required for OpenAI-compatible providers")
        if _is_official_openai_base_url(base_url) and not api_key:
            raise ValueError("api_key is required for the official OpenAI endpoint")
        return settings
    if provider in {"anthropic", "claude"}:
        if not api_key:
            raise ValueError("api_key is required for Anthropic")
        return settings
    raise ValueError(f"unsupported provider: {settings.provider}")


def call_transport(
    transport: Transport,
    url: str,
    headers: dict[str, str],
    payload: dict[str, Any],
    timeout: float,
) -> dict[str, Any]:
    if transport is default_transport:
        return transport(url, headers, payload, timeout)
    return transport(url, headers, payload)


def strip_markdown_fence(text: str) -> str:
    value = text.strip()
    match = re.fullmatch(r"```(?:json|jsonl)?\s*(.*?)\s*```", value, flags=re.DOTALL)
    return match.group(1).strip() if match else value


def safe_preview(text: str, limit: int = 240) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    return compact[:limit]


def relaxed_json_string(value: str) -> str:
    return (
        value.replace("\\n", "\n")
        .replace("\\r", "\r")
        .replace("\\t", "\t")
        .replace('\\"', '"')
        .replace("\\/", "/")
    )


def parse_relaxed_jsonl_rows(value: str) -> list[dict]:
    start = value.find("{")
    if start == -1:
        return []
    payload = value[start:].strip()
    chunks = re.split(r"}\s*(?={)", payload)
    rows: list[dict] = []
    for chunk in chunks:
        chunk = chunk.strip()
        if not chunk:
            continue
        if not chunk.endswith("}"):
            chunk = f"{chunk}}}"
        try:
            parsed = json.loads(chunk)
            if isinstance(parsed, dict):
                rows.append(parsed)
                continue
        except json.JSONDecodeError:
            pass

        id_match = re.search(r'"id"\s*:\s*"((?:\\.|[^"\\])*)"', chunk)
        html_match = re.search(r'"translated_html"\s*:\s*"', chunk)
        if not id_match or not html_match:
            return []
        translated_html = chunk[html_match.end() :].strip()
        if translated_html.endswith("}"):
            translated_html = translated_html[:-1].rstrip()
        if translated_html.endswith('"'):
            translated_html = translated_html[:-1]
        rows.append(
            {
                "id": relaxed_json_string(id_match.group(1)),
                "translated_html": relaxed_json_string(translated_html),
            }
        )
    return rows


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

    decoder = json.JSONDecoder()
    cursor = 0
    streamed_rows: list[dict] = []
    while cursor < len(value):
        while cursor < len(value) and value[cursor].isspace():
            cursor += 1
        if cursor >= len(value):
            break
        if value[cursor] not in "{[":
            next_object = min(
                [index for index in (value.find("{", cursor), value.find("[", cursor)) if index != -1],
                default=-1,
            )
            if next_object == -1:
                raise ValueError(f"provider returned invalid JSONL: preview={safe_preview(value)}")
            cursor = next_object
        try:
            parsed, cursor = decoder.raw_decode(value, cursor)
        except json.JSONDecodeError:
            streamed_rows = []
            break
        if isinstance(parsed, list):
            streamed_rows.extend(row for row in parsed if isinstance(row, dict))
        elif isinstance(parsed, dict):
            streamed_rows.append(parsed)
        else:
            raise ValueError(f"provider returned non-object JSON content: preview={safe_preview(value)}")
    if streamed_rows:
        return streamed_rows

    rows: list[dict] = []
    first_error: tuple[int, json.JSONDecodeError] | None = None
    for line_number, line in enumerate(value.splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            first_error = (line_number, exc)
            break
        if not isinstance(row, dict):
            raise ValueError(f"provider returned non-object JSONL row at line {line_number}")
        rows.append(row)
    if first_error is None:
        return rows
    relaxed_rows = parse_relaxed_jsonl_rows(value)
    if relaxed_rows:
        return relaxed_rows
    line_number, exc = first_error
    raise ValueError(
        f"provider returned invalid JSONL at line {line_number}: {exc}; "
        f"preview={safe_preview(value)}"
    ) from exc


def repair_translated_row_structure(source_html: str, translated_html: str) -> str:
    try:
        source = parse_snippet(source_html)
        translated = parse_snippet(translated_html)
    except ValueError:
        return translated_html
    desired_tokens = structural_tokens(source)
    if not desired_tokens or structural_tokens(translated) == desired_tokens:
        return translated_html

    desired_counts: dict[tuple[str, str, str], int] = {}
    for token in desired_tokens:
        desired_counts[token] = desired_counts.get(token, 0) + 1

    if source.attrib:
        for attr in ("id", "href", "src"):
            if attr in source.attrib and translated.attrib.get(attr) != source.attrib[attr]:
                translated.attrib[attr] = source.attrib[attr]

    def token_for(element: ET.Element) -> tuple[str, str, str] | None:
        for attr in ("id", "href", "src"):
            value = element.attrib.get(attr)
            if value is not None:
                return (local_name(element.tag), attr, value)
        return None

    def prune_extra_structural_children(parent: ET.Element) -> None:
        for child in list(parent):
            prune_extra_structural_children(child)
            token = token_for(child)
            if token is not None and token not in desired_counts:
                parent.remove(child)

    prune_extra_structural_children(translated)
    present = structural_tokens(translated)
    present_counts: dict[tuple[str, str, str], int] = {}
    for token in present:
        present_counts[token] = present_counts.get(token, 0) + 1

    missing_elements: list[ET.Element] = []
    for source_descendant in source.iter():
        token = token_for(source_descendant)
        if token is None:
            continue
        if present_counts.get(token, 0) >= desired_counts[token]:
            continue
        clone = ET.Element(local_name(source_descendant.tag), dict(source_descendant.attrib))
        clone.text = ""
        clone.tail = ""
        missing_elements.append(clone)
        present_counts[token] = present_counts.get(token, 0) + 1

    for clone in reversed(missing_elements):
        translated.insert(0, clone)
    return element_to_snippet(translated)


def repair_translated_rows_structure(batch_rows: list[dict], translated_rows: list[dict]) -> list[dict]:
    source_by_id = {row.get("id"): row for row in batch_rows}
    repaired: list[dict] = []
    for row in translated_rows:
        source = source_by_id.get(row.get("id"))
        translated_html = row.get("translated_html")
        if source is not None and isinstance(translated_html, str):
            row = dict(row)
            row["translated_html"] = repair_translated_row_structure(
                str(source.get("source_html", "")),
                translated_html,
            )
        repaired.append(row)
    return repaired


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
        "This is a neutral literary translation and format-preservation task. "
        "Return JSONL even when source text contains mature themes, profanity, romance, conflict, or quoted speech; "
        "do not refuse, moralize, summarize, or add safety commentary. "
        "Return only JSONL rows with exactly `id` and `translated_html`. "
        "Do not add markdown, commentary, summaries, or placeholder text. "
        "Do not prefix or suffix the JSONL with any non-JSON text. "
        "Escape quotes and control characters so every line is valid JSON. "
        "Return exactly one row for every input id, and never omit anchors. "
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
        request_timeout: float = DEFAULT_REQUEST_TIMEOUT,
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
        self.request_timeout = normalize_request_timeout(request_timeout)
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
        response = call_transport(self.transport, endpoint, headers, payload, self.request_timeout)
        self._record_response_usage(response)
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
        request_timeout: float = DEFAULT_REQUEST_TIMEOUT,
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
        self.request_timeout = normalize_request_timeout(request_timeout)
        self.transport = transport

    def translate_batch(self, rows: list[dict], glossary: str, context: str) -> list[dict]:
        messages = batch_prompt(rows, glossary, context, self.target_language)
        system = messages[0]["content"]
        user = messages[1]["content"]
        response = call_transport(
            self.transport,
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
            self.request_timeout,
        )
        self._record_response_usage(response)
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
    settings = validate_provider_settings(settings)
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
            request_timeout=settings.request_timeout,
        )
    if provider in {"anthropic", "claude"}:
        return AnthropicProvider(
            base_url=settings.base_url or "https://api.anthropic.com/v1",
            api_key=settings.api_key,
            model=settings.model,
            target_language=settings.target_language,
            temperature=settings.temperature,
            request_timeout=settings.request_timeout,
        )
    raise ValueError(f"unsupported provider: {settings.provider}")
