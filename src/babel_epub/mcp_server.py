"""Minimal stdio MCP server for Claude Desktop integrations."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from . import __version__
from .jobs import BabelJobEngine, JobRequest
from .providers import (
    DEFAULT_MAX_CONCURRENCY,
    DEFAULT_MAX_RETRIES,
    DEFAULT_REQUEST_TIMEOUT,
    ProviderSettings,
    normalize_budget_limit,
    normalize_cost_per_1m,
    normalize_max_concurrency,
    normalize_max_retries,
    normalize_rate_limit,
    normalize_request_timeout,
)


def tool(name: str, description: str, properties: dict[str, Any], required: list[str] | None = None) -> dict:
    return {
        "name": name,
        "description": description,
        "inputSchema": {
            "type": "object",
            "properties": properties,
            "required": required or [],
        },
    }

START_TRANSLATION_PROPERTIES = {
    "job_id": {"type": "string"},
    "provider": {"type": "string", "default": "openai-compatible"},
    "base_url": {"type": "string"},
    "api_key": {"type": "string"},
    "model": {"type": "string"},
    "target_language": {"type": "string", "default": "Simplified Chinese"},
    "resume": {"type": "boolean", "default": False},
    "batch_filter": {"type": "array", "items": {"type": "integer"}, "description": "Optional batch numbers to translate/retry."},
    "max_concurrency": {"type": "integer", "default": DEFAULT_MAX_CONCURRENCY, "minimum": 1, "maximum": 8},
    "request_timeout": {"type": "number", "default": DEFAULT_REQUEST_TIMEOUT, "minimum": 30},
    "max_retries": {"type": "integer", "default": DEFAULT_MAX_RETRIES, "minimum": 0, "maximum": 5},
    "structured_output_enabled": {"type": "boolean", "default": False},
    "memory_enabled": {"type": "boolean", "default": False},
    "memory_project_id": {"type": "string", "description": "Optional project or series id for Translation Memory reuse."},
    "memory_path": {"type": "string", "description": "Optional explicit Translation Memory JSON path."},
    "ai_qa_enabled": {"type": "boolean", "default": True},
    "auto_title_enabled": {"type": "boolean", "default": False},
    "max_requests_per_minute": {"type": "integer", "default": 0},
    "max_tokens_per_minute": {"type": "integer", "default": 0},
    "budget_limit": {"type": "number", "default": 0},
    "input_cost_per_1m_tokens": {"type": "number", "default": 0},
    "output_cost_per_1m_tokens": {"type": "number", "default": 0},
}


TOOLS = [
    tool(
        "prepare_epub",
        "Prepare an ebook workspace from a local file path and choose the final output format.",
        {
            "path": {"type": "string"},
            "target_language": {"type": "string", "default": "Simplified Chinese"},
            "title": {"type": "string"},
            "language": {"type": "string", "default": "zh-CN"},
            "output_format": {"type": "string", "default": "epub"},
            "max_chars": {"type": "integer", "description": "Optional approximate source character budget per batch."},
            "max_tokens": {"type": "integer", "description": "Optional estimated token budget per batch."},
            "glossary_preset": {"type": "string", "description": "Optional built-in preset name or JSON preset path."},
        },
        ["path"],
    ),
    tool(
        "start_translation",
        "Start translating a prepared Babel job.",
        START_TRANSLATION_PROPERTIES,
        ["job_id", "provider"],
    ),
    tool("job_status", "Return Babel job status.", {"job_id": {"type": "string"}}, ["job_id"]),
    tool(
        "update_glossary",
        "Replace the glossary for a prepared Babel job.",
        {"job_id": {"type": "string"}, "content": {"type": "string"}},
        ["job_id", "content"],
    ),
    tool("list_jobs", "List known Babel jobs, newest first.", {}, []),
    tool(
        "artifact_path",
        "Return a local artifact path for a Babel job without reading private book contents.",
        {"job_id": {"type": "string"}, "artifact": {"type": "string", "enum": ["output", "epub", "report", "audit", "ai-report", "glossary", "work-dir"]}},
        ["job_id", "artifact"],
    ),
    tool("read_glossary_terms", "Return structured glossary terms for a Babel job.", {"job_id": {"type": "string"}}, ["job_id"]),
    tool(
        "update_glossary_terms",
        "Replace structured glossary terms for a Babel job.",
        {"job_id": {"type": "string"}, "glossary_terms": {"type": "array", "items": {"type": "object"}}},
        ["job_id", "glossary_terms"],
    ),
    tool(
        "import_glossary",
        "Import structured glossary terms as csv, tbx, markdown, or json.",
        {"job_id": {"type": "string"}, "content": {"type": "string"}, "format": {"type": "string", "default": "csv"}, "mode": {"type": "string", "default": "upsert"}, "default_status": {"type": "string", "default": "pending"}},
        ["job_id", "content"],
    ),
    tool(
        "export_glossary",
        "Export structured glossary terms as csv, tbx, markdown, or json.",
        {"job_id": {"type": "string"}, "format": {"type": "string", "default": "csv"}},
        ["job_id"],
    ),
    tool(
        "resume_failed_job",
        "Resume a failed Babel job using existing valid batch outputs.",
        {"job_id": {"type": "string"}, **START_TRANSLATION_PROPERTIES},
        ["job_id", "provider"],
    ),
    tool(
        "retry_batch",
        "Delete one translated batch output, then resume the job so only missing/invalid batches rerun.",
        {"job_id": {"type": "string"}, "batch": {"type": "integer"}, **START_TRANSLATION_PROPERTIES},
        ["job_id", "batch", "provider"],
    ),
]


def provider_settings_from_arguments(arguments: dict[str, Any]) -> ProviderSettings:
    return ProviderSettings(
        provider=arguments.get("provider", "openai-compatible"),
        base_url=arguments.get("base_url", ""),
        api_key=arguments.get("api_key", ""),
        model=arguments.get("model", ""),
        target_language=arguments.get("target_language", "Simplified Chinese"),
        request_timeout=normalize_request_timeout(arguments.get("request_timeout", DEFAULT_REQUEST_TIMEOUT)),
        max_retries=normalize_max_retries(arguments.get("max_retries", DEFAULT_MAX_RETRIES)),
        max_concurrency=normalize_max_concurrency(arguments.get("max_concurrency", DEFAULT_MAX_CONCURRENCY)),
        structured_output_enabled=arguments.get("structured_output_enabled") is True,
        memory_enabled=arguments.get("memory_enabled") is True,
        memory_project_id=arguments.get("memory_project_id", ""),
        memory_path=arguments.get("memory_path", ""),
        max_requests_per_minute=normalize_rate_limit(arguments.get("max_requests_per_minute", 0)),
        max_tokens_per_minute=normalize_rate_limit(arguments.get("max_tokens_per_minute", 0)),
        budget_limit=normalize_budget_limit(arguments.get("budget_limit", 0)),
        input_cost_per_1m_tokens=normalize_cost_per_1m(arguments.get("input_cost_per_1m_tokens", 0)),
        output_cost_per_1m_tokens=normalize_cost_per_1m(arguments.get("output_cost_per_1m_tokens", 0)),
    )


def artifact_path_for(job, artifact: str) -> Path:
    mapping = {
        "output": job.output_book,
        "epub": job.output_epub or job.work_dir / "output.epub",
        "report": job.report_path,
        "audit": job.audit_path,
        "ai-report": job.ai_quality_report_path,
        "glossary": job.glossary_path,
        "work-dir": job.work_dir,
    }
    path = mapping.get(artifact)
    if path is None:
        raise ValueError(f"artifact is not available: {artifact}")
    return Path(path)


def translated_batch_path(job, batch_number: int) -> Path:
    manifest_path = job.work_dir / "pipeline" / "batch_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for batch in manifest:
        if int(batch.get("batch", -1)) == int(batch_number):
            return job.work_dir / "pipeline" / batch["output"]
    raise ValueError(f"batch not found: {batch_number}")


class BabelMCP:
    def __init__(self) -> None:
        self.engine = BabelJobEngine(Path(os.environ.get("BABEL_DATA_DIR", "./babel-mcp-data")))

    def handle(self, message: dict[str, Any]) -> dict[str, Any] | None:
        method = message.get("method")
        request_id = message.get("id")
        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "babel-mcp", "version": __version__},
                },
            }
        if method == "notifications/initialized":
            return None
        if method == "tools/list":
            return {"jsonrpc": "2.0", "id": request_id, "result": {"tools": TOOLS}}
        if method == "tools/call":
            params = message.get("params", {})
            name = params.get("name")
            arguments = params.get("arguments", {})
            try:
                result = self.call_tool(name, arguments)
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}]},
                }
            except Exception as exc:
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {"code": -32000, "message": str(exc)},
                }
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32601, "message": "method not found"}}

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if name == "prepare_epub":
            path = Path(arguments["path"])
            job = self.engine.create_job(
                JobRequest(
                    filename=path.name,
                    content=path.read_bytes(),
                    target_language=arguments.get("target_language", "Simplified Chinese"),
                    title=arguments.get("title", ""),
                    language=arguments.get("language", "zh-CN"),
                    output_format=arguments.get("output_format", "epub"),
                    max_chars=arguments.get("max_chars"),
                    max_tokens=arguments.get("max_tokens"),
                    glossary_preset=arguments.get("glossary_preset", ""),
                )
            )
            return {"job": job.to_dict(include_paths=True), "glossary": self.engine.read_glossary(job.job_id)}
        if name == "start_translation":
            job = self.engine.start_job(
                arguments["job_id"],
                provider_settings_from_arguments(arguments),
                resume=arguments.get("resume") is True,
                ai_qa_enabled=arguments.get("ai_qa_enabled", True) is not False,
                auto_title_enabled=arguments.get("auto_title_enabled") is True,
                batch_filter=[int(value) for value in arguments.get("batch_filter", [])],
            )
            return {"job": job.to_dict(include_paths=True)}
        if name == "job_status":
            return {"job": self.engine.get_job(arguments["job_id"]).to_dict(include_paths=True)}
        if name == "update_glossary":
            job = self.engine.update_glossary(arguments["job_id"], arguments["content"])
            return {"job": job.to_dict(include_paths=True)}
        if name == "list_jobs":
            return {"jobs": [job.to_dict(include_paths=True) for job in self.engine.list_jobs()]}
        if name == "artifact_path":
            job = self.engine.get_job(arguments["job_id"])
            path = artifact_path_for(job, arguments.get("artifact", "output"))
            return {"job_id": job.job_id, "artifact": arguments.get("artifact", "output"), "path": str(path)}
        if name == "read_glossary_terms":
            return {"glossary_terms": self.engine.read_glossary_terms(arguments["job_id"])}
        if name == "update_glossary_terms":
            job = self.engine.update_glossary_terms(arguments["job_id"], list(arguments.get("glossary_terms") or []))
            return {"job": job.to_dict(include_paths=True), "glossary_terms": self.engine.read_glossary_terms(job.job_id)}
        if name == "import_glossary":
            job, terms, summary = self.engine.import_glossary_terms(
                arguments["job_id"],
                arguments.get("content", ""),
                fmt=arguments.get("format", "csv"),
                default_status=arguments.get("default_status", "pending"),
                mode=arguments.get("mode", "upsert"),
            )
            return {"job": job.to_dict(include_paths=True), "glossary_terms": terms, "summary": summary}
        if name == "export_glossary":
            fmt = arguments.get("format", "csv")
            return {"format": fmt, "content": self.engine.export_glossary_terms(arguments["job_id"], fmt=fmt)}
        if name == "resume_failed_job":
            job = self.engine.start_job(
                arguments["job_id"],
                provider_settings_from_arguments(arguments),
                resume=True,
                ai_qa_enabled=arguments.get("ai_qa_enabled", True) is not False,
                auto_title_enabled=arguments.get("auto_title_enabled") is True,
                batch_filter=[int(value) for value in arguments.get("batch_filter", [])],
            )
            return {"job": job.to_dict(include_paths=True)}
        if name == "retry_batch":
            job = self.engine.get_job(arguments["job_id"])
            if job.status == "running":
                raise ValueError("cannot retry a batch while the job is running")
            output = translated_batch_path(job, int(arguments["batch"]))
            if output.exists():
                output.unlink()
            job = self.engine.start_job(
                arguments["job_id"],
                provider_settings_from_arguments(arguments),
                resume=True,
                ai_qa_enabled=arguments.get("ai_qa_enabled", True) is not False,
                auto_title_enabled=arguments.get("auto_title_enabled") is True,
                batch_filter=[int(arguments["batch"])],
            )
            return {"job": job.to_dict(include_paths=True), "cleared_batch": int(arguments["batch"]), "cleared_output": str(output)}
        raise ValueError(f"unknown tool: {name}")


def main() -> None:
    server = BabelMCP()
    for line in sys.stdin:
        if not line.strip():
            continue
        response = server.handle(json.loads(line))
        if response is not None:
            sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
