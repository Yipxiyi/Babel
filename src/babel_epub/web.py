"""Self-hosted Web UI and API server for Babel."""

from __future__ import annotations

import json
import mimetypes
import os
import re
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

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


STATIC_DIR = Path(__file__).with_name("static")
FALLBACK_INDEX_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Babel · Ebook Translation Workbench</title>
</head>
<body>
  <div id="root">
    <h1>Babel</h1>
    <p>Static Web UI has not been built yet. Run npm run build --prefix web.</p>
    <p>Guide · Start with upload · View current job · Resume Translation</p>
    <div id="terminalLog" data-api-loader="loadLatestJob">/api/jobs</div>
  </div>
</body>
</html>
"""


def render_index_html() -> str:
    index_path = STATIC_DIR / "index.html"
    if index_path.exists():
        return index_path.read_text(encoding="utf-8")
    return FALLBACK_INDEX_HTML


@dataclass(frozen=True)
class FormPart:
    name: str
    value: str = ""
    content: bytes = b""
    filename: str = ""


class BabelWebHandler(BaseHTTPRequestHandler):
    engine: BabelJobEngine

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/jobs":
            self._send_json({"jobs": [job.to_dict(include_paths=False) for job in self.engine.list_jobs()]})
            return
        parts = [unquote(part) for part in path.strip("/").split("/")]
        if len(parts) == 3 and parts[:2] == ["api", "jobs"]:
            self._send_job(parts[2])
            return
        if len(parts) == 5 and parts[:2] == ["api", "jobs"] and parts[3] == "download":
            self._download(parts[2], parts[4])
            return
        if path == "/":
            self._send_bytes(render_index_html().encode("utf-8"), "text/html; charset=utf-8")
            return
        if self._send_static(path):
            return
        if not path.startswith("/api/") and "." not in Path(path).name:
            self._send_bytes(render_index_html().encode("utf-8"), "text/html; charset=utf-8")
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/jobs":
            self._create_job()
            return
        parts = [unquote(part) for part in path.strip("/").split("/")]
        if len(parts) == 4 and parts[:2] == ["api", "jobs"] and parts[3] == "glossary":
            self._update_glossary(parts[2])
            return
        if len(parts) == 4 and parts[:2] == ["api", "jobs"] and parts[3] == "start":
            self._start_job(parts[2])
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def log_message(self, format: str, *args) -> None:
        if os.environ.get("BABEL_WEB_LOGS"):
            super().log_message(format, *args)

    def _send_static(self, request_path: str) -> bool:
        static_path = _resolve_static_path(request_path)
        if static_path is None:
            return False
        content_type = mimetypes.guess_type(static_path.name)[0] or "application/octet-stream"
        if static_path.suffix == ".js":
            content_type = "text/javascript; charset=utf-8"
        elif static_path.suffix in {".css", ".svg"}:
            content_type = f"{content_type}; charset=utf-8"
        self._send_bytes(static_path.read_bytes(), content_type)
        return True

    def _create_job(self) -> None:
        try:
            form = _parse_multipart_form(
                content_type=self.headers.get("Content-Type", ""),
                body=self.rfile.read(int(self.headers.get("Content-Length", "0"))),
            )
        except ValueError as exc:
            self.send_error(HTTPStatus.BAD_REQUEST, str(exc))
            return
        file_item = form.get("epub")
        if file_item is None or not file_item.content:
            self.send_error(HTTPStatus.BAD_REQUEST, "missing epub upload")
            return
        filename = Path(file_item.filename or "input.epub").name
        try:
            job = self.engine.create_job(
                JobRequest(
                    filename=filename,
                    content=file_item.content,
                    target_language=_field_value(form, "target_language", "Simplified Chinese"),
                    title=_field_value(form, "title", ""),
                    language=_field_value(form, "language", "zh-CN"),
                    output_format=_field_value(form, "output_format", "epub"),
                )
            )
        except ValueError as exc:
            self.send_error(HTTPStatus.BAD_REQUEST, str(exc))
            return
        self._send_json({"job": job.to_dict(include_paths=False), "glossary": self.engine.read_glossary(job.job_id)})

    def _send_job(self, job_id: str) -> None:
        try:
            job = self.engine.get_job(job_id)
            glossary = self.engine.read_glossary(job_id)
        except KeyError:
            self.send_error(HTTPStatus.NOT_FOUND, "job not found")
            return
        self._send_json({"job": job.to_dict(include_paths=False), "glossary": glossary})

    def _update_glossary(self, job_id: str) -> None:
        try:
            content = self.rfile.read(int(self.headers.get("Content-Length", "0"))).decode("utf-8")
            job = self.engine.update_glossary(job_id, content)
        except KeyError:
            self.send_error(HTTPStatus.NOT_FOUND, "job not found")
            return
        self._send_json({"job": job.to_dict(include_paths=False), "glossary": content})

    def _start_job(self, job_id: str) -> None:
        try:
            data = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))).decode("utf-8"))
            job = self.engine.start_job(
                job_id,
                ProviderSettings(
                    provider=data.get("provider", "openai-compatible"),
                    base_url=data.get("base_url", ""),
                    api_key=data.get("api_key", ""),
                    model=data.get("model", ""),
                    target_language=data.get("target_language", "Simplified Chinese"),
                    temperature=float(data.get("temperature", 0.2)),
                    request_timeout=normalize_request_timeout(
                        data.get("request_timeout", DEFAULT_REQUEST_TIMEOUT)
                    ),
                    max_retries=normalize_max_retries(data.get("max_retries", DEFAULT_MAX_RETRIES)),
                    max_concurrency=normalize_max_concurrency(
                        data.get("max_concurrency", DEFAULT_MAX_CONCURRENCY)
                    ),
                ),
                resume=data.get("resume") is True,
            )
        except KeyError:
            self.send_error(HTTPStatus.NOT_FOUND, "job not found")
            return
        except (ValueError, json.JSONDecodeError) as exc:
            self.send_error(HTTPStatus.BAD_REQUEST, str(exc))
            return
        self._send_json({"job": job.to_dict(include_paths=False)})

    def _download(self, job_id: str, artifact: str) -> None:
        try:
            job = self.engine.get_job(job_id)
        except KeyError:
            self.send_error(HTTPStatus.NOT_FOUND, "job not found")
            return
        path_map = {
            "output": job.output_book or job.output_epub,
            "glossary": job.glossary_path,
            "report": job.report_path,
            "audit": job.audit_path,
        }
        artifact_path = path_map.get(artifact)
        if artifact_path is None or not artifact_path.exists():
            self.send_error(HTTPStatus.NOT_FOUND, "artifact not ready")
            return
        content_type = _content_type_for_download(artifact_path) if artifact == "output" else "text/plain; charset=utf-8"
        if artifact == "audit":
            content_type = "application/json; charset=utf-8"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Disposition", f'attachment; filename="{artifact_path.name}"')
        self.end_headers()
        self.wfile.write(artifact_path.read_bytes())

    def _send_json(self, data: dict, status: HTTPStatus = HTTPStatus.OK) -> None:
        self._send_bytes(json.dumps(data, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8", status)

    def _send_bytes(self, content: bytes, content_type: str, status: HTTPStatus = HTTPStatus.OK) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)


def _resolve_static_path(request_path: str) -> Path | None:
    if not STATIC_DIR.exists():
        return None
    relative = unquote(request_path).lstrip("/")
    if not relative or relative.startswith("."):
        return None
    root = STATIC_DIR.resolve()
    candidate = (STATIC_DIR / relative).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    return candidate if candidate.is_file() else None


def _parse_multipart_form(content_type: str, body: bytes) -> dict[str, FormPart]:
    match = re.search(r"boundary=(?P<boundary>[^;]+)", content_type)
    if not match:
        raise ValueError("multipart boundary missing")
    boundary = match.group("boundary").strip('"').encode("utf-8")
    delimiter = b"--" + boundary
    parts: dict[str, FormPart] = {}
    for raw_part in body.split(delimiter):
        if not raw_part or raw_part in {b"--", b"--\r\n"}:
            continue
        if raw_part.startswith(b"\r\n"):
            raw_part = raw_part[2:]
        if raw_part.endswith(b"--"):
            raw_part = raw_part[:-2]
        if raw_part.endswith(b"\r\n"):
            raw_part = raw_part[:-2]
        header_blob, _, part_body = raw_part.partition(b"\r\n\r\n")
        if not header_blob:
            continue
        headers = header_blob.decode("utf-8", errors="replace").split("\r\n")
        disposition = next(
            (line for line in headers if line.lower().startswith("content-disposition:")),
            "",
        )
        name_match = re.search(r'name="([^"]+)"', disposition)
        if not name_match:
            continue
        filename_match = re.search(r'filename="([^"]*)"', disposition)
        name = name_match.group(1)
        filename = filename_match.group(1) if filename_match else ""
        if part_body.endswith(b"\r\n"):
            part_body = part_body[:-2]
        value = "" if filename else part_body.decode("utf-8", errors="replace")
        parts[name] = FormPart(name=name, value=value, content=part_body, filename=filename)
    return parts


def _field_value(form: dict[str, FormPart], name: str, default: str) -> str:
    part = form.get(name)
    if part is None:
        return default
    return part.value if part.value else default


def _content_type_for_download(path: Path) -> str:
    return {
        ".epub": "application/epub+zip",
        ".kepub": "application/epub+zip",
        ".pdf": "application/pdf",
        ".txt": "text/plain; charset=utf-8",
        ".html": "text/html; charset=utf-8",
        ".htmlz": "application/zip",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }.get(path.suffix.lower(), "application/octet-stream")


def run_server(host: str = "127.0.0.1", port: int = 7860, data_dir: Path | None = None) -> None:
    engine = BabelJobEngine(data_dir or Path(os.environ.get("BABEL_DATA_DIR", "./babel-data")))
    handler = type("ConfiguredBabelWebHandler", (BabelWebHandler,), {"engine": engine})
    server = ThreadingHTTPServer((host, port), handler)
    print(f"Babel Web listening on http://{host}:{port}")
    server.serve_forever()


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Run Babel self-hosted Web UI")
    parser.add_argument("--host", default=os.environ.get("BABEL_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("BABEL_PORT", "7860")))
    parser.add_argument("--data-dir", default=os.environ.get("BABEL_DATA_DIR", "./babel-data"))
    args = parser.parse_args()
    run_server(host=args.host, port=args.port, data_dir=Path(args.data_dir))


if __name__ == "__main__":
    main()
