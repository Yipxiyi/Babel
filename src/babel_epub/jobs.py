"""Local job engine for Babel Web, Docker, and agent integrations."""

from __future__ import annotations

import json
import re
import shutil
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Callable
from xml.etree import ElementTree as ET

from .adaptive import adaptive_batch_char_limit, resolve_execution_plan
from .diagnostics import diagnose_error
from .glossary import (
    detect_deterministic_quality,
    detect_glossary_issues,
    glossary_summary,
    html_text,
    read_glossary_terms,
    render_glossary_markdown,
    repair_untranslated_terms,
    write_ai_quality_report,
    write_glossary_terms,
)
from .glossary_io import export_glossary_text, import_glossary_text, merge_glossary_terms
from .memory import DEFAULT_MEMORY_PROJECT_ID, TranslationMemoryStore, memory_path_for, normalize_memory_project_id
from .pipeline import (
    command_apply,
    command_audit,
    command_prepare,
    command_report,
    command_validate_batches,
    element_text,
    element_to_snippet,
    parse_snippet,
    read_jsonl,
    validate_translation_rows,
    write_jsonl,
)
from .formats import BookFormatError, normalize_extension, supported_output_extensions
from .providers import (
    DEFAULT_MAX_CONCURRENCY,
    BudgetExceededError,
    ProviderSettings,
    RateLimitState,
    estimate_cost,
    estimate_rows_tokens,
    TranslationProvider,
    is_retryable_translation_error,
    is_retryable_translation_output_error,
    make_provider,
    normalize_max_concurrency,
    normalize_max_retries,
    repair_translated_rows_structure,
    is_provider_safety_rejection,
    validate_provider_settings,
)


ProviderFactory = Callable[[ProviderSettings], TranslationProvider]
MAX_EVENTS = 500
DEFAULT_MAX_BLOCKS = 20
GLOSSARY_AUTOFILL_BATCH_SIZE = 40


def split_text_chunks(text: str, char_limit: int) -> list[str]:
    """Split prose near sentence/word boundaries without dropping source text."""
    target = max(500, int(char_limit) - 256)
    start = 0
    chunks: list[str] = []
    while len(text) - start > target:
        window = text[start : start + target + 1]
        candidates = [match.end() for match in re.finditer(r"[。！？.!?；;]\s*|\s+", window)]
        cut = max((position for position in candidates if position >= target // 2), default=target)
        chunk = text[start : start + cut]
        if not chunk:
            chunk = text[start : start + target]
            cut = target
        chunks.append(chunk)
        start += cut
    if start < len(text):
        chunks.append(text[start:])
    return chunks


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def batch_summary(batch: dict | None) -> dict | None:
    if not batch:
        return None
    return {
        "batch": batch.get("batch"),
        "file": batch.get("file", ""),
        "chapter_label": batch.get("chapter_label", ""),
        "block_count": batch.get("block_count", 0),
        "input": batch.get("input", ""),
        "output": batch.get("output", ""),
    }


def make_event(event_type: str, message: str, batch: dict | None = None, **details: object) -> dict:
    event = {"ts": utc_now(), "type": event_type, "message": message}
    summary = batch_summary(batch)
    if summary:
        event["batch"] = summary
    event.update({key: value for key, value in details.items() if value is not None})
    return event


def infer_manifest_batch(work_dir: Path, batch_number: int) -> dict | None:
    manifest_path = work_dir / "pipeline" / "batch_manifest.json"
    if not manifest_path.exists():
        return None
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    for batch in manifest:
        if batch.get("batch") == batch_number:
            return batch_summary(batch)
    return None


def default_events(data: dict, failed_batch: dict | None) -> list[dict]:
    status = data.get("status", "unknown")
    message = data.get("message") or f"Loaded existing {status} job."
    batch = failed_batch if status == "failed" else None
    return [make_event(status, message, batch=batch)]


@dataclass(frozen=True)
class JobRequest:
    filename: str
    content: bytes = b""
    target_language: str = "Simplified Chinese"
    title: str = ""
    language: str = "zh-CN"
    output_format: str = ".epub"
    max_blocks: int = DEFAULT_MAX_BLOCKS
    max_chars: int | None = None
    max_tokens: int | None = None
    glossary_preset: str = ""
    adaptive_enabled: bool = True


@dataclass
class BabelJob:
    job_id: str
    status: str
    filename: str
    input_format: str
    target_language: str
    title: str
    language: str
    output_format: str
    work_dir: Path
    input_epub: Path
    glossary_path: Path
    total_batches: int = 0
    completed_batches: int = 0
    block_count: int = 0
    message: str = ""
    output_epub: Path | None = None
    output_book: Path | None = None
    audit_path: Path | None = None
    report_path: Path | None = None
    ai_quality_report_path: Path | None = None
    current_batch: dict | None = None
    failed_batch: dict | None = None
    active_batches: list[dict] = field(default_factory=list)
    failed_batches: list[dict] = field(default_factory=list)
    max_concurrency: int = DEFAULT_MAX_CONCURRENCY
    last_active_at: str = ""
    events: list[dict] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    ai_qa_status: str = "pending"
    ai_qa_summary: dict = field(default_factory=dict)
    ai_fix_summary: dict = field(default_factory=dict)
    glossary_summary: dict = field(default_factory=dict)
    usage_summary: dict = field(default_factory=dict)
    memory_summary: dict = field(default_factory=dict)
    memory_project_id: str = ""
    generated_title: str = ""
    title_source: str = "manual"
    glossary_preset: str = ""
    adaptive_enabled: bool = True
    adaptive_plan: dict = field(default_factory=dict)
    diagnostics: list[dict] = field(default_factory=list)

    def to_dict(self, include_paths: bool = True) -> dict:
        data = asdict(self)
        path_keys = (
            "work_dir",
            "input_epub",
            "glossary_path",
            "output_epub",
            "output_book",
            "audit_path",
            "report_path",
            "ai_quality_report_path",
        )
        for key in path_keys:
            value = data.get(key)
            if value is not None:
                data[key] = str(value)
        if not include_paths:
            for key in path_keys:
                data.pop(key, None)
        return data


class Namespace:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class BabelJobEngine:
    def __init__(
        self,
        data_dir: Path,
        provider_factory: ProviderFactory = make_provider,
    ) -> None:
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.provider_factory = provider_factory
        self._jobs: dict[str, BabelJob] = {}
        self._threads: dict[str, threading.Thread] = {}
        self._start_locks: dict[str, threading.Lock] = {}
        self._rate_limiters: dict[str, RateLimitState] = {}
        self._memory_stores: dict[Path, TranslationMemoryStore] = {}
        self._budget_locks: dict[str, threading.Lock] = {}
        self._budget_reservations: dict[str, float] = {}
        self._lock = threading.Lock()
        self._load_existing_jobs()

    def _load_existing_jobs(self) -> None:
        for state_path in self.data_dir.glob("*/job.json"):
            try:
                data = json.loads(state_path.read_text(encoding="utf-8"))
                job = self._job_from_dict(data)
                if job.status in {"running", "preparing"}:
                    job.status = "failed"
                    job.active_batches = []
                    job.current_batch = None
                    job.message = "Interrupted before completion. Resume to continue from valid translated batches."
                    job.errors.append("job was interrupted before completion")
                    self._append_event(job, "failed", job.message, batch=job.failed_batch)
                    self._save_job(job)
                self._jobs[job.job_id] = job
            except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
                continue

    def _job_from_dict(self, data: dict) -> BabelJob:
        work_dir = Path(data["work_dir"])
        failed_batch = data.get("failed_batch")
        if failed_batch is None and data.get("status") == "failed":
            failed_batch = infer_manifest_batch(work_dir, int(data.get("completed_batches", 0)) + 1)
        active_batches = list(data.get("active_batches") or [])
        failed_batches = list(data.get("failed_batches") or ([failed_batch] if failed_batch else []))
        events = list(data.get("events") or default_events(data, failed_batch))
        last_active_at = data.get("last_active_at") or (events[-1]["ts"] if events else utc_now())
        adaptive_plan = dict(data.get("adaptive_plan") or {})
        adaptive_enabled = bool(data.get("adaptive_enabled", adaptive_plan.get("enabled", False)))
        return BabelJob(
            job_id=data["job_id"],
            status=data["status"],
            filename=data["filename"],
            input_format=data.get("input_format", ".epub"),
            target_language=data["target_language"],
            title=data.get("title", ""),
            language=data.get("language", "zh-CN"),
            output_format=data.get("output_format", ".epub"),
            work_dir=work_dir,
            input_epub=Path(data["input_epub"]),
            glossary_path=Path(data["glossary_path"]),
            total_batches=int(data.get("total_batches", 0)),
            completed_batches=int(data.get("completed_batches", 0)),
            block_count=int(data.get("block_count", 0)),
            message=data.get("message", ""),
            output_epub=Path(data["output_epub"]) if data.get("output_epub") else None,
            output_book=Path(data["output_book"]) if data.get("output_book") else None,
            audit_path=Path(data["audit_path"]) if data.get("audit_path") else None,
            report_path=Path(data["report_path"]) if data.get("report_path") else None,
            ai_quality_report_path=Path(data["ai_quality_report_path"])
            if data.get("ai_quality_report_path")
            else None,
            current_batch=data.get("current_batch"),
            failed_batch=failed_batch,
            active_batches=active_batches,
            failed_batches=failed_batches,
            max_concurrency=normalize_max_concurrency(data.get("max_concurrency", DEFAULT_MAX_CONCURRENCY)),
            last_active_at=last_active_at,
            events=events,
            errors=list(data.get("errors", [])),
            ai_qa_status=data.get("ai_qa_status", "pending"),
            ai_qa_summary=dict(data.get("ai_qa_summary") or {}),
            ai_fix_summary=dict(data.get("ai_fix_summary") or {}),
            glossary_summary=dict(data.get("glossary_summary") or {}),
            usage_summary=dict(data.get("usage_summary") or {}),
            memory_summary=dict(data.get("memory_summary") or {}),
            memory_project_id=data.get("memory_project_id", ""),
            generated_title=data.get("generated_title", ""),
            title_source=data.get("title_source", "manual"),
            glossary_preset=data.get("glossary_preset", ""),
            adaptive_enabled=adaptive_enabled,
            adaptive_plan=adaptive_plan,
            diagnostics=list(data.get("diagnostics") or []),
        )

    def _save_job(self, job: BabelJob) -> None:
        job.work_dir.mkdir(parents=True, exist_ok=True)
        state_path = job.work_dir / "job.json"
        tmp_path = state_path.with_suffix(".json.tmp")
        tmp_path.write_text(
            json.dumps(job.to_dict(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        tmp_path.replace(state_path)

    def _set_job(self, job: BabelJob) -> BabelJob:
        with self._lock:
            self._jobs[job.job_id] = job
            self._save_job(job)
            return job

    def _mutate_job(self, job_id: str, mutator: Callable[[BabelJob], None]) -> BabelJob:
        with self._lock:
            if job_id not in self._jobs:
                raise KeyError(job_id)
            job = self._jobs[job_id]
            mutator(job)
            self._save_job(job)
            return job

    def _append_event(
        self,
        job: BabelJob,
        event_type: str,
        message: str,
        batch: dict | None = None,
        **details: object,
    ) -> None:
        event = make_event(event_type, message, batch=batch, **details)
        job.events.append(event)
        job.events = job.events[-MAX_EVENTS:]
        job.last_active_at = event["ts"]

    def _set_active_current(self, job: BabelJob) -> None:
        job.current_batch = job.active_batches[0] if job.active_batches else None

    def _remove_active_batch(self, job: BabelJob, batch_number: int) -> None:
        job.active_batches = [
            active for active in job.active_batches if int(active.get("batch", -1)) != batch_number
        ]
        self._set_active_current(job)

    def _record_provider_usage(
        self,
        job_id: str,
        provider: TranslationProvider,
        scope: str,
        settings: ProviderSettings | None = None,
        estimated: dict | None = None,
    ) -> None:
        snapshot = provider.usage_snapshot()
        baseline = dict(getattr(provider, "_babel_recorded_usage", {}))
        usage = {
            key: max(0, int(snapshot.get(key, 0)) - int(baseline.get(key, 0)))
            for key in ("requests", "prompt_tokens", "completion_tokens", "total_tokens")
        }
        provider._babel_recorded_usage = snapshot  # type: ignore[attr-defined]
        estimated = dict(estimated or {})
        if not any(usage.values()) and not estimated:
            return
        actual_cost = 0.0
        estimated_cost_value = 0.0
        if settings is not None:
            actual_cost = estimate_cost(
                settings,
                usage.get("prompt_tokens", 0),
                usage.get("completion_tokens", 0),
            )
            estimated_cost_value = estimate_cost(
                settings,
                int(estimated.get("prompt_tokens", 0)),
                int(estimated.get("completion_tokens", 0)),
            )

        def mutate(job: BabelJob) -> None:
            current = dict(job.usage_summary or {})
            by_scope = dict(current.get("by_scope") or {})
            scoped = dict(by_scope.get(scope) or {})
            for key in ("requests", "prompt_tokens", "completion_tokens", "total_tokens"):
                if usage.get(key):
                    current[key] = int(current.get(key, 0)) + int(usage.get(key, 0))
                    scoped[key] = int(scoped.get(key, 0)) + int(usage.get(key, 0))
            if estimated:
                current["estimated_requests"] = int(current.get("estimated_requests", 0)) + 1
                scoped["estimated_requests"] = int(scoped.get("estimated_requests", 0)) + 1
                for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
                    estimate_key = f"estimated_{key}"
                    current[estimate_key] = int(current.get(estimate_key, 0)) + int(estimated.get(key, 0))
                    scoped[estimate_key] = int(scoped.get(estimate_key, 0)) + int(estimated.get(key, 0))
            if actual_cost:
                current["actual_cost"] = round(float(current.get("actual_cost", 0.0)) + actual_cost, 6)
                scoped["actual_cost"] = round(float(scoped.get("actual_cost", 0.0)) + actual_cost, 6)
            if estimated_cost_value:
                current["estimated_cost"] = round(float(current.get("estimated_cost", 0.0)) + estimated_cost_value, 6)
                scoped["estimated_cost"] = round(float(scoped.get("estimated_cost", 0.0)) + estimated_cost_value, 6)
            if settings is not None and settings.budget_limit:
                current["budget_limit"] = float(settings.budget_limit)
            current["budget_spent"] = round(
                max(float(current.get("actual_cost", 0.0)), float(current.get("estimated_cost", 0.0))),
                6,
            )
            by_scope[scope] = scoped
            current["by_scope"] = by_scope
            job.usage_summary = current

        self._mutate_job(job_id, mutate)

    def _rate_limiter_for(self, job_id: str, settings: ProviderSettings) -> RateLimitState:
        key = job_id
        with self._lock:
            limiter = self._rate_limiters.get(key)
            if limiter is None:
                limiter = RateLimitState(settings.max_requests_per_minute, settings.max_tokens_per_minute)
                self._rate_limiters[key] = limiter
            return limiter

    def _enforce_provider_budget(
        self,
        job_id: str,
        settings: ProviderSettings,
        estimated: dict,
        scope: str,
        batch: dict | None = None,
    ) -> None:
        estimated_cost_value = estimate_cost(
            settings,
            int(estimated.get("prompt_tokens", 0)),
            int(estimated.get("completion_tokens", 0)),
        )
        if not settings.budget_limit or not estimated_cost_value:
            return
        current_job = self.get_job(job_id)
        usage = dict(current_job.usage_summary or {})
        spent = max(float(usage.get("actual_cost", 0.0)), float(usage.get("estimated_cost", 0.0)))
        reserved = float(self._budget_reservations.get(job_id, 0.0))
        if spent + reserved + estimated_cost_value <= float(settings.budget_limit):
            return
        message = (
            f"Provider budget would be exceeded for {scope}: "
            f"spent or reserved ${spent + reserved:.6f}, next request estimated ${estimated_cost_value:.6f}, "
            f"limit ${float(settings.budget_limit):.6f}."
        )

        def mutate(job: BabelJob) -> None:
            current = dict(job.usage_summary or {})
            current["budget_limit"] = float(settings.budget_limit)
            current["budget_spent"] = round(spent, 6)
            current["budget_exceeded"] = True
            job.usage_summary = current
            self._append_event(job, "budget-stop", message, batch=batch)

        self._mutate_job(job_id, mutate)
        raise BudgetExceededError(message)

    def _provider_translate_once(
        self,
        job_id: str,
        settings: ProviderSettings,
        provider: TranslationProvider,
        rows: list[dict],
        glossary: str,
        context: str,
        scope: str,
        batch: dict | None = None,
    ) -> list[dict]:
        estimated = estimate_rows_tokens(rows, glossary, context)
        estimated_cost_value = estimate_cost(
            settings,
            int(estimated.get("prompt_tokens", 0)),
            int(estimated.get("completion_tokens", 0)),
        )
        budget_lock: threading.Lock | None = None
        if settings.budget_limit and estimated_cost_value:
            with self._lock:
                budget_lock = self._budget_locks.setdefault(job_id, threading.Lock())
            with budget_lock:
                self._enforce_provider_budget(job_id, settings, estimated, scope, batch=batch)
                self._budget_reservations[job_id] = (
                    float(self._budget_reservations.get(job_id, 0.0)) + estimated_cost_value
                )
        limiter = self._rate_limiter_for(job_id, settings)
        delay = limiter.acquire(int(estimated.get("total_tokens", 0)))
        if delay:
            self._mutate_job(
                job_id,
                lambda job: self._append_event(
                    job,
                    "rate-limit",
                    f"Waited {delay:.1f}s for provider rate limits.",
                    batch=batch,
                    delay_seconds=round(delay, 3),
                ),
            )
        try:
            return provider.translate_batch(rows, glossary=glossary, context=context)
        finally:
            if budget_lock is None:
                self._record_provider_usage(job_id, provider, scope, settings=settings, estimated=estimated)
            else:
                with budget_lock:
                    try:
                        self._record_provider_usage(job_id, provider, scope, settings=settings, estimated=estimated)
                    finally:
                        remaining = max(
                            0.0,
                            float(self._budget_reservations.get(job_id, 0.0)) - estimated_cost_value,
                        )
                        if remaining:
                            self._budget_reservations[job_id] = remaining
                        else:
                            self._budget_reservations.pop(job_id, None)

    def _memory_store_for(self, settings: ProviderSettings) -> TranslationMemoryStore | None:
        if not settings.memory_enabled:
            return None
        project_id = normalize_memory_project_id(settings.memory_project_id or DEFAULT_MEMORY_PROJECT_ID)
        path = memory_path_for(self.data_dir, project_id=project_id, memory_path=settings.memory_path or None)
        resolved_path = path.resolve()
        with self._lock:
            store = self._memory_stores.get(resolved_path)
            if store is None:
                store = TranslationMemoryStore(resolved_path, project_id=project_id)
                self._memory_stores[resolved_path] = store
            return store

    def _record_memory_event(
        self,
        job_id: str,
        event_type: str,
        message: str,
        memory_store: TranslationMemoryStore,
        batch: dict | None = None,
        **details: object,
    ) -> None:
        stats = memory_store.stats()

        def mutate(job: BabelJob) -> None:
            job.memory_summary = stats
            job.memory_project_id = str(stats.get("project_id", ""))
            self._append_event(job, event_type, message, batch=batch, **details)

        self._mutate_job(job_id, mutate)

    def _start_batch(self, job_id: str, batch: dict, attempt: int) -> None:
        summary = batch_summary(batch)

        def mutate(job: BabelJob) -> None:
            batch_number = int(batch["batch"])
            job.active_batches = [
                active for active in job.active_batches if int(active.get("batch", -1)) != batch_number
            ]
            if summary:
                job.active_batches.append(summary)
            self._set_active_current(job)
            job.message = (
                f"Translating batch {batch['batch']}/{job.total_batches}: "
                f"{batch.get('chapter_label') or batch.get('file')}"
            )
            self._append_event(job, "batch-start", job.message, batch=batch, attempt=attempt)

        self._mutate_job(job_id, mutate)

    def _retry_batch(self, job_id: str, batch: dict, next_attempt: int, max_attempts: int, error: Exception) -> None:
        def mutate(job: BabelJob) -> None:
            self._append_event(
                job,
                "batch-retry",
                f"Retrying batch {batch['batch']} attempt {next_attempt}/{max_attempts}: {error}",
                batch=batch,
                attempt=next_attempt,
            )

        self._mutate_job(job_id, mutate)

    def _finish_batch(self, job_id: str, batch: dict) -> None:
        def mutate(job: BabelJob) -> None:
            self._remove_active_batch(job, int(batch["batch"]))
            job.completed_batches += 1
            job.message = (
                f"Translated {job.completed_batches}/{job.total_batches} batches "
                f"with {len(job.active_batches)} active."
            )
            self._append_event(job, "batch-done", job.message, batch=batch)

        self._mutate_job(job_id, mutate)

    def _fail_batch(self, job_id: str, batch: dict, error: Exception) -> None:
        summary = batch_summary(batch)

        def mutate(job: BabelJob) -> None:
            batch_number = int(batch["batch"])
            self._remove_active_batch(job, batch_number)
            if summary and not any(
                int(failed.get("batch", -1)) == batch_number for failed in job.failed_batches
            ):
                job.failed_batches.append(summary)
            if job.failed_batch is None:
                job.failed_batch = summary
            job.errors.append(str(error))
            job.diagnostics.append(
                diagnose_error(
                    error,
                    stage="translate",
                    filename=job.filename,
                    input_format=job.input_format,
                    batch=summary,
                )
            )
            job.message = f"Batch {batch['batch']} failed; continuing remaining batches."
            self._append_event(job, "batch-failed", f"Batch {batch['batch']} failed: {error}", batch=batch)

        self._mutate_job(job_id, mutate)

    def _batch_issues(self, pipeline_dir: Path, batch: dict) -> list[str]:
        batch_path = pipeline_dir / batch["input"]
        out_path = pipeline_dir / batch["output"]
        if not out_path.exists():
            return [f"missing output: {out_path}"]
        try:
            return validate_translation_rows(read_jsonl(batch_path), read_jsonl(out_path))
        except Exception as exc:
            return [str(exc)]

    def _valid_resume_batch_numbers(self, pipeline_dir: Path, manifest: list[dict]) -> set[int]:
        valid: set[int] = set()
        for batch in manifest:
            if not self._batch_issues(pipeline_dir, batch):
                valid.add(int(batch["batch"]))
        return valid

    def _reserve_job(self, request: JobRequest) -> tuple[BabelJob, Path]:
        job_id = uuid.uuid4().hex[:12]
        work_dir = self.data_dir / job_id
        output_format = normalize_extension(request.output_format, ".epub")
        if output_format not in supported_output_extensions():
            raise BookFormatError(
                f"unsupported output format: {output_format}. Supported: {', '.join(supported_output_extensions())}"
            )
        extension = Path(request.filename).suffix.lower() or ".book"
        input_book = work_dir / f"upload{extension}"
        glossary_path = work_dir / "translation_glossary.md"
        work_dir.mkdir(parents=True, exist_ok=True)
        title = request.title or default_output_title(request.filename, request.target_language)
        job = BabelJob(
            job_id=job_id,
            status="preparing",
            filename=request.filename,
            input_format=extension,
            target_language=request.target_language,
            title=title,
            language=request.language,
            output_format=output_format,
            work_dir=work_dir,
            input_epub=work_dir / "input.epub",
            glossary_path=glossary_path,
            message="Analyzing the source file and choosing safe translation settings.",
            title_source="manual" if request.title else "suffix",
            glossary_preset=request.glossary_preset,
            adaptive_enabled=request.adaptive_enabled,
        )
        self._append_event(job, "preparing", job.message)
        return self._set_job(job), input_book

    def _prepare_reserved_job(
        self,
        job_id: str,
        request: JobRequest,
        input_book: Path,
        *,
        raise_on_error: bool = False,
    ) -> BabelJob:
        job = self.get_job(job_id)
        try:
            result = command_prepare(
                Namespace(
                    input_book=input_book,
                    input_epub=None,
                    work_dir=job.work_dir,
                    glossary=job.glossary_path,
                    target_language=request.target_language,
                    max_blocks=request.max_blocks,
                    max_chars=request.max_chars,
                    max_tokens=request.max_tokens,
                    glossary_preset=request.glossary_preset,
                    adaptive_enabled=request.adaptive_enabled,
                    source_filename=request.filename,
                    force=True,
                )
            )
            input_metadata = result["input_metadata"]
            blocks = result["blocks"]
            manifest = result["batches"]
            plan = result["adaptive_plan"]
            if not blocks:
                raise RuntimeError("No translatable text blocks were detected in the source file.")
            terms = read_glossary_terms(job.work_dir)

            def prepared(current: BabelJob) -> None:
                current.status = "prepared"
                current.input_format = input_metadata.get("input_format", current.input_format)
                current.total_batches = len(manifest)
                current.block_count = len(blocks)
                current.adaptive_plan = plan
                current.glossary_summary = glossary_summary(terms)
                current.message = "Prepared. Review the glossary, then start translation."
                self._append_event(
                    current,
                    "prepared",
                    f"Prepared {len(manifest)} batches from {len(blocks)} blocks with "
                    f"{'adaptive' if current.adaptive_enabled else 'custom'} settings.",
                )

            return self._mutate_job(job_id, prepared)
        except Exception as exc:
            failed = self._mark_job_failed(job_id, exc, stage="prepare")
            if raise_on_error:
                raise
            return failed

    def create_job(self, request: JobRequest) -> BabelJob:
        job, input_book = self._reserve_job(request)
        try:
            input_book.write_bytes(request.content)
        except OSError as exc:
            self._mark_job_failed(job.job_id, exc, stage="upload")
            raise
        return self._prepare_reserved_job(job.job_id, request, input_book, raise_on_error=True)

    def create_job_from_file_async(self, request: JobRequest, uploaded_path: Path) -> BabelJob:
        job, input_book = self._reserve_job(request)
        try:
            shutil.move(str(uploaded_path), input_book)
        except Exception as exc:
            try:
                uploaded_path.unlink(missing_ok=True)
            except OSError:
                pass
            return self._mark_job_failed(job.job_id, exc, stage="upload")
        thread = threading.Thread(
            target=self._prepare_reserved_job,
            args=(job.job_id, request, input_book),
            daemon=True,
        )
        with self._lock:
            self._threads[job.job_id] = thread
        thread.start()
        return self.get_job(job.job_id)

    def list_jobs(self) -> list[BabelJob]:
        with self._lock:
            return sorted(self._jobs.values(), key=lambda job: (job.last_active_at, job.job_id), reverse=True)

    def get_job(self, job_id: str) -> BabelJob:
        with self._lock:
            if job_id not in self._jobs:
                raise KeyError(job_id)
            return self._jobs[job_id]

    def read_glossary(self, job_id: str) -> str:
        return self.get_job(job_id).glossary_path.read_text(encoding="utf-8")

    def read_glossary_terms(self, job_id: str) -> list[dict]:
        job = self.get_job(job_id)
        terms = read_glossary_terms(job.work_dir)
        if terms:
            return terms
        return self._refresh_glossary_from_terms(job)

    def _refresh_glossary_from_terms(self, job: BabelJob) -> list[dict]:
        terms = read_glossary_terms(job.work_dir)
        if not terms:
            pipeline_dir = job.work_dir / "pipeline"
            from .glossary import build_glossary_terms

            terms = build_glossary_terms(pipeline_dir, job.target_language, glossary_preset=job.glossary_preset)
        job.glossary_path.write_text(
            render_glossary_markdown(job.target_language, terms),
            encoding="utf-8",
        )
        job.glossary_summary = glossary_summary(terms)
        self._save_job(job)
        return terms

    def update_glossary(self, job_id: str, content: str) -> BabelJob:
        job = self.get_job(job_id)
        job.glossary_path.write_text(content, encoding="utf-8")
        job.message = "Glossary updated."
        self._append_event(job, "glossary", "Glossary updated.")
        return self._set_job(job)

    def update_glossary_terms(self, job_id: str, terms: list[dict]) -> BabelJob:
        job = self.get_job(job_id)
        normalized = write_glossary_terms(job.work_dir, terms)
        job.glossary_path.write_text(
            render_glossary_markdown(job.target_language, normalized),
            encoding="utf-8",
        )
        job.glossary_summary = glossary_summary(normalized)
        job.message = "Glossary terms updated."
        self._append_event(job, "glossary", "Structured glossary terms updated.")
        return self._set_job(job)

    def import_glossary_terms(
        self,
        job_id: str,
        content: str,
        fmt: str = "csv",
        default_status: str = "pending",
        mode: str = "upsert",
    ) -> tuple[BabelJob, list[dict], dict]:
        job = self.get_job(job_id)
        imported = import_glossary_text(content, fmt, default_status=default_status)
        existing = self.read_glossary_terms(job_id)
        merged = merge_glossary_terms(existing, imported, mode=mode)
        normalized = write_glossary_terms(job.work_dir, merged)
        job.glossary_path.write_text(
            render_glossary_markdown(job.target_language, normalized),
            encoding="utf-8",
        )
        job.glossary_summary = glossary_summary(normalized)
        summary = {
            "imported": len(imported),
            "total": len(normalized),
            "mode": mode,
            "format": fmt,
            "default_status": default_status,
        }
        job.message = f"Imported {len(imported)} glossary term{'s' if len(imported) != 1 else ''}."
        self._append_event(job, "glossary-import", job.message, **summary)
        return self._set_job(job), normalized, summary

    def export_glossary_terms(self, job_id: str, fmt: str = "csv") -> str:
        job = self.get_job(job_id)
        return export_glossary_text(self.read_glossary_terms(job_id), fmt, target_language=job.target_language)

    def autofill_glossary_terms(self, job_id: str, settings: ProviderSettings) -> BabelJob:
        validate_provider_settings(settings)
        provider = self.provider_factory(settings)
        job = self.get_job(job_id)
        terms = self.read_glossary_terms(job_id)
        candidates = [
            (index, term)
            for index, term in enumerate(terms)
            if str(term.get("status", "pending")) == "pending"
            and not str(term.get("translation", "")).strip()
            and str(term.get("source", "")).strip()
        ]
        filled = 0
        glossary = render_glossary_markdown(job.target_language, terms)
        context = (
            "Translate glossary term candidates into concise, reusable target-language terms. "
            "For names, provide a natural transliteration. For places, species, titles, and recurring terms, "
            "provide a short stable translation. Return only the translated XHTML rows."
        )
        for offset in range(0, len(candidates), GLOSSARY_AUTOFILL_BATCH_SIZE):
            batch = candidates[offset : offset + GLOSSARY_AUTOFILL_BATCH_SIZE]
            rows = [
                {
                    "id": f"glossary-term::{index}",
                    "source_text": str(term.get("source", "")),
                    "source_html": f"<p>{escape(str(term.get('source', '')))}</p>",
                }
                for index, term in batch
            ]
            translated_rows = self._provider_translate_once(
                job_id,
                settings,
                provider,
                rows,
                glossary,
                context,
                "glossary",
            )
            translated_by_id = {str(row.get("id", "")): row for row in translated_rows}
            for index, term in batch:
                row = translated_by_id.get(f"glossary-term::{index}")
                if not row:
                    continue
                translation = html_text(str(row.get("translated_html", ""))).strip()
                if not translation:
                    continue
                if str(term.get("status", "pending")) != "pending" or str(term.get("translation", "")).strip():
                    continue
                term["translation"] = translation
                term["locked"] = False
                filled += 1

        normalized = write_glossary_terms(job.work_dir, terms)
        job.glossary_path.write_text(
            render_glossary_markdown(job.target_language, normalized),
            encoding="utf-8",
        )
        job.glossary_summary = glossary_summary(normalized)
        job.message = (
            f"AI filled {filled} glossary draft translation{'s' if filled != 1 else ''}."
            if filled
            else "No empty pending glossary terms needed AI draft translations."
        )
        self._append_event(job, "glossary-autofill", job.message, filled=filled)
        return self._set_job(job)

    def _mark_job_failed(
        self,
        job_id: str,
        error: Exception,
        batch: dict | None = None,
        *,
        stage: str = "translate",
    ) -> BabelJob:
        error_text = str(error)

        def mutate(job: BabelJob) -> None:
            failed_batch = batch_summary(batch) if batch else job.current_batch or job.failed_batch
            job.status = "failed"
            job.active_batches = []
            job.current_batch = None
            job.failed_batch = failed_batch
            if failed_batch and not any(
                int(failed.get("batch", -1)) == int(failed_batch.get("batch", -2))
                for failed in job.failed_batches
            ):
                job.failed_batches.append(failed_batch)
            job.errors.append(error_text)
            job.diagnostics.append(
                diagnose_error(
                    error,
                    stage=stage,
                    filename=job.filename,
                    input_format=job.input_format,
                    batch=failed_batch,
                )
            )
            job.message = f"Failed: {error_text}"
            batch_label = f" batch {failed_batch['batch']}" if failed_batch else ""
            self._append_event(job, "failed", f"Failed{batch_label}: {error_text}", batch=failed_batch)

        return self._mutate_job(job_id, mutate)

    def _mark_job_failed_after_batches(self, job_id: str) -> BabelJob:
        def mutate(job: BabelJob) -> None:
            job.status = "failed"
            job.active_batches = []
            job.current_batch = None
            job.failed_batch = job.failed_batches[0] if job.failed_batches else job.failed_batch
            failed_count = len(job.failed_batches)
            last_error = job.errors[-1] if job.errors else ""
            error_suffix = f" Last error: {last_error}" if last_error else ""
            job.message = (
                f"Failed {failed_count} batch{'es' if failed_count != 1 else ''}; "
                f"fix provider/configuration and resume.{error_suffix}"
            )
            self._append_event(job, "failed", job.message, batch=job.failed_batch)

        return self._mutate_job(job_id, mutate)

    def start_job(
        self,
        job_id: str,
        settings: ProviderSettings,
        resume: bool = False,
        ai_qa_enabled: bool = True,
        auto_title_enabled: bool = False,
        batch_filter: list[int] | None = None,
    ) -> BabelJob:
        with self._lock:
            if job_id not in self._jobs:
                raise KeyError(job_id)
            start_lock = self._start_locks.setdefault(job_id, threading.Lock())

        # Serialize the complete check/validate/start transition for each job. Without
        # this lock, a duplicate request with invalid settings can mark an already
        # running job as failed while its original worker continues writing output.
        with start_lock:
            job = self.get_job(job_id)
            if job.status == "running":
                return job
            if job.status == "preparing":
                raise ValueError(
                    "The source file is still being prepared. Wait for preparation to finish before starting."
                )
            manifest_path = job.work_dir / "pipeline" / "batch_manifest.json"
            if job.block_count <= 0 or not manifest_path.exists():
                raise ValueError(
                    "This source file was not prepared successfully. Review its diagnostic and upload it again."
                )
            if job.status == "completed":
                raise ValueError("This translation job is already completed.")
            try:
                resolved_settings, _ = resolve_execution_plan(job.adaptive_plan, settings)
                validate_provider_settings(resolved_settings)
            except ValueError as exc:
                self._mark_job_failed(job_id, exc, stage="settings")
                raise

            thread = threading.Thread(
                target=self.run_job,
                args=(job_id, settings, resume, ai_qa_enabled, auto_title_enabled, batch_filter),
                daemon=True,
            )
            with self._lock:
                job = self._jobs[job_id]
                job.status = "running"
                job.current_batch = None
                job.active_batches = []
                job.failed_batch = None
                job.failed_batches = []
                job.message = "Starting translation job."
                self._append_event(job, "run-starting", job.message)
                self._threads[job_id] = thread
                self._save_job(job)
            try:
                thread.start()
            except RuntimeError as exc:
                self._mark_job_failed(job_id, exc, stage="translate")
                raise
            return self.get_job(job_id)

    def _translate_batch_with_retries(
        self,
        job_id: str,
        settings: ProviderSettings,
        pipeline_dir: Path,
        batch: dict,
        glossary: str,
        context: str,
        memory_store: TranslationMemoryStore | None = None,
    ) -> None:
        batch_rows = read_jsonl(pipeline_dir / batch["input"])
        out_path = pipeline_dir / batch["output"]
        max_retries = normalize_max_retries(settings.max_retries)
        max_attempts = max_retries + 1
        attempt = 1
        while True:
            self._start_batch(job_id, batch, attempt)
            try:
                memory_rows: list[dict] = []
                rows_to_translate: list[dict] = []
                if memory_store is not None:
                    for row in batch_rows:
                        hit = memory_store.lookup(row, settings.target_language)
                        if hit is not None and not validate_translation_rows([row], [hit.row]):
                            memory_rows.append(hit.row)
                        else:
                            rows_to_translate.append(row)
                    if memory_rows:
                        self._record_memory_event(
                            job_id,
                            "memory-hit",
                            f"Reused {len(memory_rows)} row{'s' if len(memory_rows) != 1 else ''} from translation memory.",
                            memory_store,
                            batch=batch,
                            hit_count=len(memory_rows),
                        )
                else:
                    rows_to_translate = list(batch_rows)

                provider_rows: list[dict] = []
                if rows_to_translate:
                    provider = self.provider_factory(settings)
                    try:
                        provider_rows = self._translate_rows_with_safety_fallback(
                            job_id,
                            settings,
                            provider,
                            batch,
                            rows_to_translate,
                            glossary,
                            context,
                        )
                    finally:
                        pass
                    provider_rows = repair_translated_rows_structure(rows_to_translate, provider_rows)

                translated_by_id = {str(row.get("id", "")): row for row in memory_rows + provider_rows}
                translated_rows = [translated_by_id.get(str(row.get("id", "")), {}) for row in batch_rows]
                translated_rows = repair_translated_rows_structure(batch_rows, translated_rows)
                issues = validate_translation_rows(batch_rows, translated_rows)
                if issues:
                    raise ValueError(f"{out_path} has validation issues:\n" + "\n".join(issues[:20]))
                write_jsonl(out_path, translated_rows)
                if memory_store is not None:
                    written = memory_store.upsert_rows(
                        batch_rows,
                        translated_rows,
                        target_language=settings.target_language,
                        source_project=memory_store.project_id,
                    )
                    if written:
                        self._record_memory_event(
                            job_id,
                            "memory-write",
                            f"Wrote {written} row{'s' if written != 1 else ''} to translation memory.",
                            memory_store,
                            batch=batch,
                            write_count=written,
                        )
                return
            except Exception as exc:
                if attempt < max_attempts and is_retryable_translation_error(exc):
                    next_attempt = attempt + 1
                    self._retry_batch(job_id, batch, next_attempt, max_attempts, exc)
                    attempt = next_attempt
                    continue
                raise

    def _translate_rows_with_safety_fallback(
        self,
        job_id: str,
        settings: ProviderSettings,
        provider: TranslationProvider,
        batch: dict,
        rows: list[dict],
        glossary: str,
        context: str,
    ) -> list[dict]:
        if len(rows) == 1:
            split_row = self._split_oversized_simple_row(job_id, batch, rows[0])
            if split_row:
                translated_parts = self._translate_rows_with_safety_fallback(
                    job_id,
                    settings,
                    provider,
                    batch,
                    split_row,
                    glossary,
                    context,
                )
                translated_text = "".join(
                    "".join(parse_snippet(str(part.get("translated_html", ""))).itertext())
                    for part in translated_parts
                )
                source_root = parse_snippet(str(rows[0].get("source_html", "")))
                merged_root = ET.Element(source_root.tag, dict(source_root.attrib))
                merged_root.text = translated_text
                return [{"id": rows[0]["id"], "translated_html": element_to_snippet(merged_root)}]

        try:
            translated_rows = self._provider_translate_once(
                job_id,
                settings,
                provider,
                rows,
                glossary,
                context,
                "translation",
                batch=batch,
            )
            translated_rows = repair_translated_rows_structure(rows, translated_rows)
            issues = validate_translation_rows(rows, translated_rows)
            if issues:
                raise ValueError("provider output has validation issues:\n" + "\n".join(issues[:20]))
            return translated_rows
        except Exception as exc:
            lowered = str(exc).lower()
            split_worthy = (
                is_provider_safety_rejection(exc)
                or is_retryable_translation_output_error(exc)
                or isinstance(exc, TimeoutError)
                or "timed out" in lowered
                or "timeout" in lowered
                or "context" in lowered
                or "request too large" in lowered
                or "too many tokens" in lowered
            )
            if len(rows) <= 1 or not split_worthy:
                raise

        chunk_size = max(1, len(rows) // 2)

        def split_event(job: BabelJob) -> None:
            self._append_event(
                job,
                "batch-split",
                (
                    f"Batch {batch['batch']} could not complete at its current size; "
                    f"retrying {len(rows)} rows in smaller chunks."
                ),
                batch=batch,
                chunk_size=chunk_size,
                row_count=len(rows),
            )

        self._mutate_job(job_id, split_event)
        translated: list[dict] = []
        for offset in range(0, len(rows), chunk_size):
            translated.extend(
                self._translate_rows_with_safety_fallback(
                    job_id,
                    settings,
                    provider,
                    batch,
                    rows[offset : offset + chunk_size],
                    glossary,
                    context,
                )
            )
        return translated

    def _split_oversized_simple_row(self, job_id: str, batch: dict, row: dict) -> list[dict]:
        job = self.get_job(job_id)
        char_limit = adaptive_batch_char_limit(job.adaptive_plan)
        source_html = str(row.get("source_html", ""))
        if len(source_html) <= char_limit:
            return []
        try:
            root = parse_snippet(source_html)
        except ValueError:
            return []
        if list(root):
            return []
        source_text = str(root.text if root.text is not None else row.get("source_text", ""))
        chunks = split_text_chunks(source_text, char_limit)
        if len(chunks) <= 1:
            return []

        parts: list[dict] = []
        for index, chunk in enumerate(chunks, start=1):
            part_root = ET.Element(root.tag, dict(root.attrib))
            part_root.text = chunk
            parts.append(
                {
                    **row,
                    "id": f"{row['id']}::part{index:03d}",
                    "source_text": chunk,
                    "source_html": element_to_snippet(part_root),
                }
            )

        self._mutate_job(
            job_id,
            lambda current: self._append_event(
                current,
                "block-split",
                f"Split one oversized source block into {len(parts)} translation requests.",
                batch=batch,
                source_row_id=row.get("id"),
                part_count=len(parts),
            ),
        )
        return parts

    def _run_ai_quality_checks(
        self,
        job_id: str,
        pipeline_dir: Path,
        enabled: bool,
    ) -> None:
        if not enabled:
            report = {
                "enabled": False,
                "status": "skipped",
                "detected": 0,
                "fixed": 0,
                "remaining": 0,
                "blocking_remaining": 0,
                "nonblocking_remaining": 0,
                "quality": detect_deterministic_quality(pipeline_dir, []),
                "issues": [],
            }
            path = write_ai_quality_report(pipeline_dir, report)

            def skipped(job: BabelJob) -> None:
                job.ai_qa_status = "skipped"
                job.ai_quality_report_path = path
                job.ai_qa_summary = report
                self._append_event(job, "ai-qa-skip", "AI quality checks skipped by settings.")

            self._mutate_job(job_id, skipped)
            return

        job = self.get_job(job_id)
        terms = self.read_glossary_terms(job_id)
        total_detected = 0
        total_fixed = 0
        remaining: list[dict] = []
        self._mutate_job(
            job_id,
            lambda current: self._append_event(
                current,
                "ai-qa-start",
                "Checking glossary consistency and untranslated locked terms.",
            ),
        )
        for round_number in range(1, 3):
            issues = detect_glossary_issues(pipeline_dir, terms)
            total_detected += len(issues) if round_number == 1 else 0
            if not issues:
                remaining = []
                break
            fixed = repair_untranslated_terms(pipeline_dir, terms, issues)
            total_fixed += fixed
            self._mutate_job(
                job_id,
                lambda current, count=fixed, number=round_number: self._append_event(
                    current,
                    "ai-qa-fix",
                    f"AI QA repair round {number} fixed {count} translated rows.",
                ),
            )
            remaining = detect_glossary_issues(pipeline_dir, terms)
            blocking = [issue for issue in remaining if issue.get("kind") == "untranslated-source-term"]
            if not blocking:
                break
        blocking_glossary_remaining = [issue for issue in remaining if issue.get("kind") == "untranslated-source-term"]
        quality = detect_deterministic_quality(pipeline_dir, terms)
        blocking_remaining_count = len(blocking_glossary_remaining) + int(quality.get("blocking_count", 0))
        nonblocking_remaining = len(remaining) - len(blocking_glossary_remaining) + int(quality.get("nonblocking_count", 0))
        combined_issues = [*remaining, *quality.get("issues", [])]
        report = {
            "enabled": True,
            "status": "failed" if blocking_remaining_count else "passed",
            "detected": total_detected + int(quality.get("issue_count", 0)),
            "fixed": total_fixed,
            "remaining": len(combined_issues),
            "blocking_remaining": blocking_remaining_count,
            "nonblocking_remaining": nonblocking_remaining,
            "glossary_issues": remaining[:200],
            "quality": quality,
            "issues": combined_issues[:200],
        }
        path = write_ai_quality_report(pipeline_dir, report)

        def finish(job: BabelJob) -> None:
            job.ai_qa_status = report["status"]
            job.ai_quality_report_path = path
            job.ai_qa_summary = {
                "detected": report["detected"],
                "remaining": report["remaining"],
                "blocking_remaining": report["blocking_remaining"],
                "nonblocking_remaining": report["nonblocking_remaining"],
                "untranslated_ratio": report["quality"].get("untranslated_ratio", 0.0),
                "long_untranslated_segments": len(report["quality"].get("long_untranslated_segments", [])),
                "punctuation_quote_drift": len(report["quality"].get("punctuation_quote_drift", [])),
                "person_name_drift": len(report["quality"].get("person_name_drift", [])),
            }
            job.ai_fix_summary = {"fixed": total_fixed, "rounds": 2 if remaining else 1}
            message = (
                f"AI QA fixed {total_fixed} rows; {blocking_remaining_count} blocking issues remain."
                if blocking_remaining_count
                else f"AI QA fixed {total_fixed} rows; no blocking glossary issues remain."
            )
            self._append_event(job, "ai-qa-done", message)

        self._mutate_job(job_id, finish)
        if blocking_remaining_count:
            raise RuntimeError(
                "AI QA found blocking quality issues after repair: "
                + "; ".join(issue["message"] for issue in combined_issues if issue.get("severity", "blocking") == "blocking")[:500]
            )

    def _maybe_generate_title(
        self,
        job_id: str,
        settings: ProviderSettings,
        provider: TranslationProvider,
        glossary: str,
        enabled: bool,
    ) -> None:
        if not enabled:
            return
        job = self.get_job(job_id)
        source_title = Path(job.filename).stem
        if not source_title:
            return
        try:
            rows = [
                {
                    "id": "book-title",
                    "source_text": source_title,
                    "source_html": f"<p>{escape(source_title)}</p>",
                }
            ]
            translated = self._provider_translate_once(
                job_id,
                settings,
                provider,
                rows,
                glossary,
                "Translate this ebook title naturally. Return only the translated title row.",
                "title",
            )
            generated = html_text(str(translated[0].get("translated_html", ""))).strip()
        except Exception:
            generated = ""
        if not generated:
            generated = default_output_title(job.filename, settings.target_language)

        def mutate(job: BabelJob) -> None:
            job.title = generated
            job.generated_title = generated
            job.title_source = "generated"
            self._append_event(job, "title", f"Generated output title: {generated}")

        self._mutate_job(job_id, mutate)

    def _finalize_completed_job(self, job_id: str, pipeline_dir: Path, ai_qa_enabled: bool) -> BabelJob:
        self._mutate_job(
            job_id,
            lambda job: self._append_event(job, "validating", "Validating all translated batches."),
        )
        try:
            command_validate_batches(Namespace(pipeline_dir=pipeline_dir))
        except SystemExit as exc:
            raise RuntimeError(f"translated batch validation failed with exit code {exc.code}") from exc

        self._run_ai_quality_checks(job_id, pipeline_dir, ai_qa_enabled)

        self._mutate_job(
            job_id,
            lambda job: self._append_event(job, "validating", "Revalidating translated batches after AI QA."),
        )
        try:
            command_validate_batches(Namespace(pipeline_dir=pipeline_dir))
        except SystemExit as exc:
            raise RuntimeError(f"post-QA batch validation failed with exit code {exc.code}") from exc

        job = self.get_job(job_id)
        output_epub = job.work_dir / "output.epub"
        output_format = normalize_extension(job.output_format, ".epub")
        output_book = job.work_dir / f"output{output_format}"
        self._mutate_job(
            job_id,
            lambda current: self._append_event(current, "packaging", f"Packaging final {output_format} output."),
        )
        command_apply(
            Namespace(
                work_dir=job.work_dir,
                output_book=output_book,
                output_epub=None,
                output_format=output_format,
                converter_path=None,
                conversion_timeout=None,
                title=job.title or None,
                language=job.language,
            )
        )
        audit_path = pipeline_dir / "epub_audit.json"
        command_audit(Namespace(epub=output_epub, out=audit_path))
        report_path = job.work_dir / "translation_report.md"
        command_report(
            Namespace(
                work_dir=job.work_dir,
                output_book=output_book,
                output_epub=None,
                glossary=job.glossary_path,
                report=report_path,
            )
        )

        def mutate(job: BabelJob) -> None:
            job.status = "completed"
            job.output_epub = output_epub
            job.output_book = output_book
            job.audit_path = audit_path
            job.report_path = report_path
            job.active_batches = []
            job.current_batch = None
            job.failed_batch = None
            job.failed_batches = []
            job.message = "Completed."
            self._append_event(job, "completed", "Completed. Output, audit, and report are ready.")

        return self._mutate_job(job_id, mutate)

    def run_job(
        self,
        job_id: str,
        settings: ProviderSettings,
        resume: bool = False,
        ai_qa_enabled: bool = True,
        auto_title_enabled: bool = False,
        batch_filter: list[int] | None = None,
    ) -> BabelJob:
        try:
            job = self.get_job(job_id)
            settings, execution_plan = resolve_execution_plan(job.adaptive_plan, settings)
            validate_provider_settings(settings)
            # Catch provider setup failures before marking the job as actively translating.
            provider = self.provider_factory(settings)
            memory_store = self._memory_store_for(settings)
            pipeline_dir = job.work_dir / "pipeline"
            translated_dir = pipeline_dir / "translated"
            translated_dir.mkdir(parents=True, exist_ok=True)
            manifest = json.loads((pipeline_dir / "batch_manifest.json").read_text(encoding="utf-8"))
            context_path = pipeline_dir / "translation_context.md"
            terms = self.read_glossary_terms(job_id)
            glossary = render_glossary_markdown(job.target_language, terms)
            job.glossary_path.write_text(glossary, encoding="utf-8")
            context = context_path.read_text(encoding="utf-8") if context_path.exists() else ""
            batch_filter_set = {int(value) for value in (batch_filter or []) if int(value) > 0} or None
            valid_resume_batches = self._valid_resume_batch_numbers(pipeline_dir, manifest) if resume or batch_filter_set else set()
            max_concurrency = normalize_max_concurrency(settings.max_concurrency)
            def apply_execution_plan(current: BabelJob) -> None:
                current.usage_summary = {}
                current.adaptive_plan = dict(current.adaptive_plan or {})
                current.adaptive_plan["execution"] = execution_plan

            self._mutate_job(job_id, apply_execution_plan)
            with self._lock:
                self._rate_limiters.pop(job_id, None)
            if memory_store is not None:
                self._record_memory_event(
                    job_id,
                    "memory-load",
                    f"Loaded translation memory project {memory_store.project_id}.",
                    memory_store,
                )
            self._maybe_generate_title(job_id, settings, provider, glossary, auto_title_enabled)

            def start_mutation(job: BabelJob) -> None:
                job.status = "running"
                job.completed_batches = len(valid_resume_batches)
                job.current_batch = None
                job.failed_batch = None
                job.active_batches = []
                job.failed_batches = []
                job.max_concurrency = max_concurrency
                job.errors = []
                job.ai_qa_status = "pending" if ai_qa_enabled else "skipped"
                job.ai_qa_summary = {}
                job.ai_fix_summary = {}
                job.glossary_summary = glossary_summary(terms)
                job.memory_summary = memory_store.stats() if memory_store is not None else {}
                job.memory_project_id = memory_store.project_id if memory_store is not None else ""
                job.message = (
                    f"Resuming translation with {job.completed_batches}/{job.total_batches} valid batches."
                    if resume
                    else f"Translating batches with up to {max_concurrency} concurrent workers."
                )
                self._append_event(job, "resume-start" if resume else "run-start", job.message)

            self._mutate_job(job_id, start_mutation)

            candidates: list[dict] = []
            for batch in manifest:
                batch_number = int(batch["batch"])
                if batch_filter_set is not None and batch_number not in batch_filter_set:
                    self._mutate_job(
                        job_id,
                        lambda current, skipped=batch: self._append_event(
                            current,
                            "batch-skip-filter",
                            f"Skipping batch {skipped['batch']}/{current.total_batches}; outside batch filter.",
                            batch=skipped,
                        ),
                    )
                    continue
                if batch_number in valid_resume_batches:
                    self._mutate_job(
                        job_id,
                        lambda current, skipped=batch: self._append_event(
                            current,
                            "batch-skip",
                            f"Skipping valid batch {skipped['batch']}/{current.total_batches}.",
                            batch=skipped,
                        ),
                    )
                    continue
                candidates.append(batch)

            if candidates:
                max_workers = min(max_concurrency, len(candidates))
                with ThreadPoolExecutor(max_workers=max_workers) as executor:
                    futures = {
                        executor.submit(
                            self._translate_batch_with_retries,
                            job_id,
                            settings,
                            pipeline_dir,
                            batch,
                            glossary,
                            context,
                            memory_store,
                        ): batch
                        for batch in candidates
                    }
                    for future in as_completed(futures):
                        batch = futures[future]
                        try:
                            future.result()
                            self._finish_batch(job_id, batch)
                        except Exception as exc:
                            self._fail_batch(job_id, batch, exc)

            if self.get_job(job_id).failed_batches:
                return self._mark_job_failed_after_batches(job_id)
            if batch_filter_set is not None:
                valid_after_filter = self._valid_resume_batch_numbers(pipeline_dir, manifest)
                if len(valid_after_filter) == len(manifest):
                    return self._finalize_completed_job(job_id, pipeline_dir, ai_qa_enabled)

                def filtered_done(job: BabelJob) -> None:
                    job.status = "prepared"
                    job.active_batches = []
                    job.current_batch = None
                    job.failed_batch = None
                    job.failed_batches = []
                    job.message = (
                        f"Batch filter completed for {len(batch_filter_set)} batch"
                        f"{'es' if len(batch_filter_set) != 1 else ''}; remaining batches are not complete."
                    )
                    self._append_event(job, "batch-filter-done", job.message)

                return self._mutate_job(job_id, filtered_done)
            return self._finalize_completed_job(job_id, pipeline_dir, ai_qa_enabled)
        except Exception as exc:
            current = self.get_job(job_id)
            latest_event = current.events[-1]["type"] if current.events else ""
            if latest_event == "packaging":
                stage = "package"
            elif latest_event.startswith("ai-qa") or latest_event == "validating":
                stage = "audit"
            else:
                stage = "translate"
            return self._mark_job_failed(job_id, exc, stage=stage)


__all__ = ["BabelJob", "BabelJobEngine", "JobRequest", "ProviderSettings"]


def default_output_title(filename: str, target_language: str) -> str:
    stem = Path(filename).stem or "Translated book"
    if "chinese" in target_language.lower() or "zh" in target_language.lower() or "中文" in target_language:
        return f"{stem}（简体中文版）"
    return f"{stem} ({target_language})"
