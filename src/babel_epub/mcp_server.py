"""Minimal stdio MCP server for Claude Desktop integrations."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from .jobs import BabelJobEngine, JobRequest
from .providers import (
    DEFAULT_MAX_CONCURRENCY,
    DEFAULT_MAX_RETRIES,
    DEFAULT_REQUEST_TIMEOUT,
    ProviderSettings,
    normalize_max_concurrency,
    normalize_max_retries,
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
        },
        ["path"],
    ),
    tool(
        "start_translation",
        "Start translating a prepared Babel job.",
        {
            "job_id": {"type": "string"},
            "provider": {"type": "string", "default": "openai-compatible"},
            "base_url": {"type": "string"},
            "api_key": {"type": "string"},
            "model": {"type": "string"},
            "target_language": {"type": "string", "default": "Simplified Chinese"},
            "resume": {"type": "boolean", "default": False},
            "max_concurrency": {"type": "integer", "default": DEFAULT_MAX_CONCURRENCY, "minimum": 1, "maximum": 8},
            "request_timeout": {"type": "number", "default": DEFAULT_REQUEST_TIMEOUT, "minimum": 30},
            "max_retries": {"type": "integer", "default": DEFAULT_MAX_RETRIES, "minimum": 0, "maximum": 5},
        },
        ["job_id", "provider", "model"],
    ),
    tool("job_status", "Return Babel job status.", {"job_id": {"type": "string"}}, ["job_id"]),
    tool(
        "update_glossary",
        "Replace the glossary for a prepared Babel job.",
        {"job_id": {"type": "string"}, "content": {"type": "string"}},
        ["job_id", "content"],
    ),
]


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
                    "serverInfo": {"name": "babel-mcp", "version": "0.6.0"},
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
                )
            )
            return {"job": job.to_dict(include_paths=True), "glossary": self.engine.read_glossary(job.job_id)}
        if name == "start_translation":
            job = self.engine.start_job(
                arguments["job_id"],
                ProviderSettings(
                    provider=arguments.get("provider", "openai-compatible"),
                    base_url=arguments.get("base_url", ""),
                    api_key=arguments.get("api_key", ""),
                    model=arguments.get("model", ""),
                    target_language=arguments.get("target_language", "Simplified Chinese"),
                    request_timeout=normalize_request_timeout(
                        arguments.get("request_timeout", DEFAULT_REQUEST_TIMEOUT)
                    ),
                    max_retries=normalize_max_retries(arguments.get("max_retries", DEFAULT_MAX_RETRIES)),
                    max_concurrency=normalize_max_concurrency(
                        arguments.get("max_concurrency", DEFAULT_MAX_CONCURRENCY)
                    ),
                ),
                resume=arguments.get("resume") is True,
            )
            return {"job": job.to_dict(include_paths=True)}
        if name == "job_status":
            return {"job": self.engine.get_job(arguments["job_id"]).to_dict(include_paths=True)}
        if name == "update_glossary":
            job = self.engine.update_glossary(arguments["job_id"], arguments["content"])
            return {"job": job.to_dict(include_paths=True)}
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
