"""Adaptive preparation and provider execution plans for Babel jobs."""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .providers import ProviderSettings


ADAPTIVE_PLAN_VERSION = 1
DEFAULT_ADAPTIVE_BATCH_CHARS = 6_000
MIN_ADAPTIVE_BATCH_CHARS = 3_000
MAX_ADAPTIVE_BATCH_CHARS = 10_000


def _percentile(values: list[int], fraction: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, math.ceil(len(ordered) * fraction) - 1))
    return ordered[index]


def _source_chars(block: dict) -> int:
    return max(1, len(str(block.get("source_html") or block.get("source_text") or "")))


def build_preparation_plan(
    *,
    filename: str,
    input_format: str,
    file_size: int,
    blocks: Iterable[dict],
    adaptive_enabled: bool,
    requested_batch_chars: int | None = None,
) -> dict:
    block_sizes = [_source_chars(block) for block in blocks]
    total_chars = sum(block_sizes)
    max_block_chars = max(block_sizes, default=0)
    p95_block_chars = _percentile(block_sizes, 0.95)

    if adaptive_enabled:
        batch_chars = DEFAULT_ADAPTIVE_BATCH_CHARS
        reasons = ["Sized batches from the uploaded file's extracted text structure."]
        if input_format.lower() == ".pdf":
            batch_chars = 4_500
            reasons.append("PDF normalization can produce unusually dense text blocks, so Babel chose smaller batches.")
        elif total_chars and total_chars < 40_000 and max_block_chars < 4_000:
            batch_chars = 8_000
            reasons.append("This is a small, well-structured document, so Babel can safely use larger batches.")
        elif total_chars > 800_000 or p95_block_chars > 3_000:
            batch_chars = 5_000
            reasons.append("Long or dense source blocks were detected, so Babel reduced the batch size.")
        batch_chars = min(max(batch_chars, MIN_ADAPTIVE_BATCH_CHARS), MAX_ADAPTIVE_BATCH_CHARS)
    else:
        batch_chars = int(requested_batch_chars or DEFAULT_ADAPTIVE_BATCH_CHARS)
        batch_chars = min(max(batch_chars, 1_000), 100_000)
        reasons = ["Using the advanced batch-size override from Settings."]

    oversized_blocks = sum(1 for size in block_sizes if size > batch_chars)
    estimated_batches = max(1, math.ceil(total_chars / batch_chars)) if block_sizes else 0
    warnings: list[dict] = []
    if not block_sizes:
        warnings.append(
            {
                "code": "no-text-detected",
                "message": "No translatable text blocks were detected.",
                "guidance": [
                    "If this is a scanned PDF, run OCR before translating.",
                    "Check that the source document is not encrypted or image-only.",
                ],
            }
        )
    if oversized_blocks:
        warnings.append(
            {
                "code": "oversized-source-blocks",
                "message": f"Detected {oversized_blocks} source block(s) larger than the target batch size.",
                "guidance": ["Babel will split simple oversized paragraphs automatically during translation."],
            }
        )

    return {
        "version": ADAPTIVE_PLAN_VERSION,
        "enabled": bool(adaptive_enabled),
        "mode": "adaptive" if adaptive_enabled else "custom",
        "source": {
            "filename": Path(filename).name,
            "input_format": input_format,
            "file_size": max(0, int(file_size)),
            "block_count": len(block_sizes),
            "total_source_chars": total_chars,
            "max_block_chars": max_block_chars,
            "p95_block_chars": p95_block_chars,
        },
        "preparation": {
            "batch_char_limit": batch_chars,
            "estimated_source_tokens_per_batch": max(1, math.ceil(batch_chars / 4)),
            "estimated_batches": estimated_batches,
            "oversized_block_count": oversized_blocks,
            "split_oversized_blocks": True,
        },
        "execution": {},
        "reasons": reasons,
        "warnings": warnings,
    }


def resolve_execution_plan(job_plan: dict, settings: "ProviderSettings") -> tuple["ProviderSettings", dict]:
    from .providers import normalize_max_concurrency, normalize_max_retries, normalize_request_timeout

    if not bool(job_plan.get("enabled", False)):
        execution = {
            "max_concurrency": normalize_max_concurrency(settings.max_concurrency),
            "request_timeout": normalize_request_timeout(settings.request_timeout),
            "max_retries": normalize_max_retries(settings.max_retries),
            "dynamic_batch_split": True,
            "reason": "Using advanced execution overrides from Settings.",
        }
        return settings, execution

    provider = settings.provider.strip().lower()
    batch_chars = int((job_plan.get("preparation") or {}).get("batch_char_limit") or DEFAULT_ADAPTIVE_BATCH_CHARS)
    local_provider = provider in {"ollama", "local", "local-openai", "local_openai"}
    machine_translation = provider in {"deepl", "deep-l", "google", "google-translate", "google_translate"}

    if local_provider:
        concurrency = 1
        timeout = 900.0
        reason = "Local providers use one worker and a longer timeout to avoid model contention."
    elif machine_translation:
        concurrency = 4
        timeout = 300.0
        reason = "The configured text-translation provider supports several compact requests concurrently."
    elif batch_chars >= 8_000:
        concurrency = 2
        timeout = 600.0
        reason = "Larger source batches use lower concurrency and a longer response window."
    else:
        concurrency = 3
        timeout = 480.0
        reason = "Balanced settings were selected for an API-hosted language model."

    retries = 2
    resolved = replace(
        settings,
        max_concurrency=concurrency,
        request_timeout=timeout,
        max_retries=retries,
    )
    execution = {
        "max_concurrency": concurrency,
        "request_timeout": timeout,
        "max_retries": retries,
        "dynamic_batch_split": True,
        "reason": reason,
    }
    return resolved, execution


def adaptive_batch_char_limit(job_plan: dict) -> int:
    return int((job_plan.get("preparation") or {}).get("batch_char_limit") or DEFAULT_ADAPTIVE_BATCH_CHARS)


__all__ = [
    "DEFAULT_ADAPTIVE_BATCH_CHARS",
    "adaptive_batch_char_limit",
    "build_preparation_plan",
    "resolve_execution_plan",
]
