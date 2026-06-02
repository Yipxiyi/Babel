"""Local job engine for Babel Web, Docker, and agent integrations."""

from __future__ import annotations

import json
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .pipeline import (
    command_apply,
    command_audit,
    command_prepare,
    command_report,
    command_validate_batches,
    read_jsonl,
    validate_translation_rows,
    write_jsonl,
)
from .formats import BookFormatError, normalize_extension, supported_output_extensions
from .providers import (
    DEFAULT_MAX_CONCURRENCY,
    ProviderSettings,
    TranslationProvider,
    is_retryable_provider_error,
    make_provider,
    normalize_max_concurrency,
    normalize_max_retries,
    validate_provider_settings,
)


ProviderFactory = Callable[[ProviderSettings], TranslationProvider]
MAX_EVENTS = 500


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
    content: bytes
    target_language: str = "Simplified Chinese"
    title: str = ""
    language: str = "zh-CN"
    output_format: str = ".epub"
    max_blocks: int = 80


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
    current_batch: dict | None = None
    failed_batch: dict | None = None
    active_batches: list[dict] = field(default_factory=list)
    failed_batches: list[dict] = field(default_factory=list)
    max_concurrency: int = DEFAULT_MAX_CONCURRENCY
    last_active_at: str = ""
    events: list[dict] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

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
        self._lock = threading.Lock()
        self._load_existing_jobs()

    def _load_existing_jobs(self) -> None:
        for state_path in self.data_dir.glob("*/job.json"):
            try:
                data = json.loads(state_path.read_text(encoding="utf-8"))
                job = self._job_from_dict(data)
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
            current_batch=data.get("current_batch"),
            failed_batch=failed_batch,
            active_batches=active_batches,
            failed_batches=failed_batches,
            max_concurrency=normalize_max_concurrency(data.get("max_concurrency", DEFAULT_MAX_CONCURRENCY)),
            last_active_at=last_active_at,
            events=events,
            errors=list(data.get("errors", [])),
        )

    def _save_job(self, job: BabelJob) -> None:
        job.work_dir.mkdir(parents=True, exist_ok=True)
        (job.work_dir / "job.json").write_text(
            json.dumps(job.to_dict(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

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

    def create_job(self, request: JobRequest) -> BabelJob:
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
        input_book.write_bytes(request.content)

        command_prepare(
            Namespace(
                input_book=input_book,
                input_epub=None,
                work_dir=work_dir,
                glossary=glossary_path,
                target_language=request.target_language,
                max_blocks=request.max_blocks,
                force=True,
            )
        )
        manifest = json.loads((work_dir / "pipeline" / "batch_manifest.json").read_text(encoding="utf-8"))
        input_metadata = json.loads((work_dir / "pipeline" / "input_format.json").read_text(encoding="utf-8"))
        blocks = read_jsonl(work_dir / "pipeline" / "blocks.jsonl")
        job = BabelJob(
            job_id=job_id,
            status="prepared",
            filename=request.filename,
            input_format=input_metadata.get("input_format", extension),
            target_language=request.target_language,
            title=request.title,
            language=request.language,
            output_format=output_format,
            work_dir=work_dir,
            input_epub=work_dir / "input.epub",
            glossary_path=glossary_path,
            total_batches=len(manifest),
            block_count=len(blocks),
            message="Prepared. Review glossary, then start translation.",
        )
        self._append_event(job, "prepared", f"Prepared {len(manifest)} batches from {len(blocks)} blocks.")
        return self._set_job(job)

    def list_jobs(self) -> list[BabelJob]:
        with self._lock:
            return sorted(self._jobs.values(), key=lambda job: job.job_id, reverse=True)

    def get_job(self, job_id: str) -> BabelJob:
        with self._lock:
            if job_id not in self._jobs:
                raise KeyError(job_id)
            return self._jobs[job_id]

    def read_glossary(self, job_id: str) -> str:
        return self.get_job(job_id).glossary_path.read_text(encoding="utf-8")

    def update_glossary(self, job_id: str, content: str) -> BabelJob:
        job = self.get_job(job_id)
        job.glossary_path.write_text(content, encoding="utf-8")
        job.message = "Glossary updated."
        self._append_event(job, "glossary", "Glossary updated.")
        return self._set_job(job)

    def _mark_job_failed(self, job_id: str, error: Exception, batch: dict | None = None) -> BabelJob:
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

    def start_job(self, job_id: str, settings: ProviderSettings, resume: bool = False) -> BabelJob:
        job = self.get_job(job_id)
        if job.status == "running":
            return job
        try:
            validate_provider_settings(settings)
        except ValueError as exc:
            self._mark_job_failed(job_id, exc)
            raise
        thread = threading.Thread(target=self.run_job, args=(job_id, settings, resume), daemon=True)
        with self._lock:
            self._threads[job_id] = thread
        thread.start()
        return self.get_job(job_id)

    def _translate_batch_with_retries(
        self,
        job_id: str,
        settings: ProviderSettings,
        pipeline_dir: Path,
        batch: dict,
        glossary: str,
        context: str,
    ) -> None:
        batch_rows = read_jsonl(pipeline_dir / batch["input"])
        out_path = pipeline_dir / batch["output"]
        max_retries = normalize_max_retries(settings.max_retries)
        max_attempts = max_retries + 1
        attempt = 1
        while True:
            self._start_batch(job_id, batch, attempt)
            try:
                provider = self.provider_factory(settings)
                translated_rows = provider.translate_batch(batch_rows, glossary=glossary, context=context)
                issues = validate_translation_rows(batch_rows, translated_rows)
                if issues:
                    raise ValueError(f"{out_path} has validation issues:\n" + "\n".join(issues[:20]))
                write_jsonl(out_path, translated_rows)
                return
            except Exception as exc:
                if attempt < max_attempts and is_retryable_provider_error(exc):
                    next_attempt = attempt + 1
                    self._retry_batch(job_id, batch, next_attempt, max_attempts, exc)
                    attempt = next_attempt
                    continue
                raise

    def _finalize_completed_job(self, job_id: str, pipeline_dir: Path) -> BabelJob:
        self._mutate_job(
            job_id,
            lambda job: self._append_event(job, "validating", "Validating all translated batches."),
        )
        try:
            command_validate_batches(Namespace(pipeline_dir=pipeline_dir))
        except SystemExit as exc:
            raise RuntimeError(f"translated batch validation failed with exit code {exc.code}") from exc

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

    def run_job(self, job_id: str, settings: ProviderSettings, resume: bool = False) -> BabelJob:
        try:
            validate_provider_settings(settings)
            # Catch provider setup failures before marking the job as actively translating.
            self.provider_factory(settings)
            job = self.get_job(job_id)
            pipeline_dir = job.work_dir / "pipeline"
            translated_dir = pipeline_dir / "translated"
            translated_dir.mkdir(parents=True, exist_ok=True)
            manifest = json.loads((pipeline_dir / "batch_manifest.json").read_text(encoding="utf-8"))
            context_path = pipeline_dir / "translation_context.md"
            glossary = job.glossary_path.read_text(encoding="utf-8")
            context = context_path.read_text(encoding="utf-8") if context_path.exists() else ""
            valid_resume_batches = self._valid_resume_batch_numbers(pipeline_dir, manifest) if resume else set()
            max_concurrency = normalize_max_concurrency(settings.max_concurrency)

            def start_mutation(job: BabelJob) -> None:
                job.status = "running"
                job.completed_batches = len(valid_resume_batches)
                job.current_batch = None
                job.failed_batch = None
                job.active_batches = []
                job.failed_batches = []
                job.max_concurrency = max_concurrency
                job.errors = []
                job.message = (
                    f"Resuming translation with {job.completed_batches}/{job.total_batches} valid batches."
                    if resume
                    else f"Translating batches with up to {max_concurrency} concurrent workers."
                )
                self._append_event(job, "resume-start" if resume else "run-start", job.message)

            self._mutate_job(job_id, start_mutation)

            candidates: list[dict] = []
            for batch in manifest:
                if int(batch["batch"]) in valid_resume_batches:
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
            return self._finalize_completed_job(job_id, pipeline_dir)
        except Exception as exc:
            return self._mark_job_failed(job_id, exc)


__all__ = ["BabelJob", "BabelJobEngine", "JobRequest", "ProviderSettings"]
