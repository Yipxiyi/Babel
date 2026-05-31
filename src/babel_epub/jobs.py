"""Local job engine for Babel Web, Docker, and agent integrations."""

from __future__ import annotations

import json
import threading
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable

from .pipeline import (
    command_apply,
    command_audit,
    command_prepare,
    command_report,
    command_validate_batches,
    read_jsonl,
    write_jsonl,
)
from .providers import ProviderSettings, TranslationProvider, make_provider


ProviderFactory = Callable[[ProviderSettings], TranslationProvider]


@dataclass(frozen=True)
class JobRequest:
    filename: str
    content: bytes
    target_language: str = "Simplified Chinese"
    title: str = ""
    language: str = "zh-CN"
    max_blocks: int = 80


@dataclass
class BabelJob:
    job_id: str
    status: str
    filename: str
    target_language: str
    title: str
    language: str
    work_dir: Path
    input_epub: Path
    glossary_path: Path
    total_batches: int = 0
    completed_batches: int = 0
    block_count: int = 0
    message: str = ""
    output_epub: Path | None = None
    audit_path: Path | None = None
    report_path: Path | None = None
    errors: list[str] = field(default_factory=list)

    def to_dict(self, include_paths: bool = True) -> dict:
        data = asdict(self)
        for key in ("work_dir", "input_epub", "glossary_path", "output_epub", "audit_path", "report_path"):
            value = data.get(key)
            if value is not None:
                data[key] = str(value)
        if not include_paths:
            for key in ("work_dir", "input_epub", "glossary_path", "output_epub", "audit_path", "report_path"):
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
        return BabelJob(
            job_id=data["job_id"],
            status=data["status"],
            filename=data["filename"],
            target_language=data["target_language"],
            title=data.get("title", ""),
            language=data.get("language", "zh-CN"),
            work_dir=Path(data["work_dir"]),
            input_epub=Path(data["input_epub"]),
            glossary_path=Path(data["glossary_path"]),
            total_batches=int(data.get("total_batches", 0)),
            completed_batches=int(data.get("completed_batches", 0)),
            block_count=int(data.get("block_count", 0)),
            message=data.get("message", ""),
            output_epub=Path(data["output_epub"]) if data.get("output_epub") else None,
            audit_path=Path(data["audit_path"]) if data.get("audit_path") else None,
            report_path=Path(data["report_path"]) if data.get("report_path") else None,
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

    def create_job(self, request: JobRequest) -> BabelJob:
        job_id = uuid.uuid4().hex[:12]
        work_dir = self.data_dir / job_id
        input_epub = work_dir / "input.epub"
        glossary_path = work_dir / "translation_glossary.md"
        work_dir.mkdir(parents=True, exist_ok=True)
        input_epub.write_bytes(request.content)

        command_prepare(
            Namespace(
                input_epub=input_epub,
                work_dir=work_dir,
                glossary=glossary_path,
                target_language=request.target_language,
                max_blocks=request.max_blocks,
                force=True,
            )
        )
        manifest = json.loads((work_dir / "pipeline" / "batch_manifest.json").read_text(encoding="utf-8"))
        blocks = read_jsonl(work_dir / "pipeline" / "blocks.jsonl")
        job = BabelJob(
            job_id=job_id,
            status="prepared",
            filename=request.filename,
            target_language=request.target_language,
            title=request.title,
            language=request.language,
            work_dir=work_dir,
            input_epub=input_epub,
            glossary_path=glossary_path,
            total_batches=len(manifest),
            block_count=len(blocks),
            message="Prepared. Review glossary, then start translation.",
        )
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
        return self._set_job(job)

    def start_job(self, job_id: str, settings: ProviderSettings) -> BabelJob:
        job = self.get_job(job_id)
        if job.status == "running":
            return job
        thread = threading.Thread(target=self.run_job, args=(job_id, settings), daemon=True)
        with self._lock:
            self._threads[job_id] = thread
        thread.start()
        return self.get_job(job_id)

    def run_job(self, job_id: str, settings: ProviderSettings) -> BabelJob:
        job = self.get_job(job_id)
        provider = self.provider_factory(settings)
        job.status = "running"
        job.completed_batches = 0
        job.errors = []
        job.message = "Translating batches."
        self._set_job(job)

        pipeline_dir = job.work_dir / "pipeline"
        translated_dir = pipeline_dir / "translated"
        translated_dir.mkdir(parents=True, exist_ok=True)
        manifest = json.loads((pipeline_dir / "batch_manifest.json").read_text(encoding="utf-8"))
        context_path = pipeline_dir / "translation_context.md"
        try:
            for batch in manifest:
                batch_rows = read_jsonl(pipeline_dir / batch["input"])
                glossary = job.glossary_path.read_text(encoding="utf-8")
                context = context_path.read_text(encoding="utf-8") if context_path.exists() else ""
                translated_rows = provider.translate_batch(batch_rows, glossary=glossary, context=context)
                out_path = pipeline_dir / batch["output"]
                write_jsonl(out_path, translated_rows)
                job.completed_batches += 1
                job.message = f"Translated {job.completed_batches}/{job.total_batches} batches."
                self._set_job(job)

            command_validate_batches(Namespace(pipeline_dir=pipeline_dir))
            output_epub = job.work_dir / "output.epub"
            command_apply(
                Namespace(
                    work_dir=job.work_dir,
                    output_epub=output_epub,
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
                    output_epub=output_epub,
                    glossary=job.glossary_path,
                    report=report_path,
                )
            )
            job.status = "completed"
            job.output_epub = output_epub
            job.audit_path = audit_path
            job.report_path = report_path
            job.message = "Completed."
            return self._set_job(job)
        except Exception as exc:
            job.status = "failed"
            job.errors.append(str(exc))
            job.message = f"Failed: {exc}"
            return self._set_job(job)


__all__ = ["BabelJob", "BabelJobEngine", "JobRequest", "ProviderSettings"]
