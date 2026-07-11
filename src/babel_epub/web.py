"""Self-hosted Web UI and API server for Babel."""

from __future__ import annotations

import hmac
import json
import mimetypes
import os
import re
from importlib import metadata
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from . import __version__
from .formats import supported_input_extensions, supported_output_extensions
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


STATIC_DIR = Path(__file__).with_name("static")
PROVIDER_SETTINGS_FILE = "provider_settings.json"
DEFAULT_MAX_UPLOAD_MB = 200
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
        if path.startswith("/api/") and not self._is_authorized_api_request():
            self.send_error(HTTPStatus.UNAUTHORIZED, "missing or invalid API token")
            return
        if path == "/api/meta":
            self._send_json(
                {
                    "version": _package_version(),
                    "github_url": "https://github.com/Yipxiyi/Babel",
                    "supported_input_formats": supported_input_extensions(),
                    "supported_output_formats": supported_output_extensions(),
                }
            )
            return
        if path == "/api/jobs":
            self._send_json({"jobs": [job.to_dict(include_paths=False) for job in self.engine.list_jobs()]})
            return
        if path == "/api/provider-settings":
            self._send_json({"provider_settings": _public_provider_settings(_read_provider_settings(self.engine.data_dir))})
            return
        parts = [unquote(part) for part in path.strip("/").split("/")]
        if len(parts) == 4 and parts[:2] == ["api", "jobs"] and parts[3] == "glossary-terms":
            self._send_glossary_terms(parts[2])
            return
        if len(parts) == 5 and parts[:2] == ["api", "jobs"] and parts[3:] == ["glossary-terms", "export"]:
            self._export_glossary_terms(parts[2])
            return
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

    def do_PUT(self) -> None:
        path = urlparse(self.path).path
        if path.startswith("/api/") and not self._is_authorized_api_request():
            self.send_error(HTTPStatus.UNAUTHORIZED, "missing or invalid API token")
            return
        parts = [unquote(part) for part in path.strip("/").split("/")]
        if len(parts) == 4 and parts[:2] == ["api", "jobs"] and parts[3] == "glossary-terms":
            self._update_glossary_terms(parts[2])
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path.startswith("/api/") and not self._is_authorized_api_request():
            self.send_error(HTTPStatus.UNAUTHORIZED, "missing or invalid API token")
            return
        if path == "/api/jobs":
            self._create_job()
            return
        parts = [unquote(part) for part in path.strip("/").split("/")]
        if len(parts) == 4 and parts[:2] == ["api", "jobs"] and parts[3] == "glossary":
            self._update_glossary(parts[2])
            return
        if len(parts) == 5 and parts[:2] == ["api", "jobs"] and parts[3:] == ["glossary-terms", "autofill"]:
            self._autofill_glossary_terms(parts[2])
            return
        if len(parts) == 5 and parts[:2] == ["api", "jobs"] and parts[3:] == ["glossary-terms", "import"]:
            self._import_glossary_terms(parts[2])
            return
        if len(parts) == 4 and parts[:2] == ["api", "jobs"] and parts[3] == "start":
            self._start_job(parts[2])
            return
        if path == "/api/provider-settings":
            self._save_provider_settings()
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def log_message(self, format: str, *args) -> None:
        if os.environ.get("BABEL_WEB_LOGS"):
            super().log_message(format, *args)

    def _is_authorized_api_request(self) -> bool:
        token = os.environ.get("BABEL_WEB_TOKEN", "").strip()
        if not token:
            return True
        bearer = self.headers.get("Authorization", "")
        if bearer.startswith("Bearer ") and hmac.compare_digest(bearer[7:].strip(), token):
            return True
        header_token = self.headers.get("X-Babel-Token", "")
        return bool(header_token) and hmac.compare_digest(header_token.strip(), token)

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
        content_length = self.headers.get("Content-Length")
        if not content_length:
            self.send_error(HTTPStatus.LENGTH_REQUIRED, "Content-Length is required")
            return
        try:
            length = int(content_length)
        except ValueError:
            self.send_error(HTTPStatus.BAD_REQUEST, "invalid Content-Length")
            return
        if length < 0:
            self.send_error(HTTPStatus.BAD_REQUEST, "invalid Content-Length")
            return
        if length > _max_upload_bytes():
            self.send_error(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "upload exceeds configured limit")
            return
        try:
            form = _parse_multipart_form(
                content_type=self.headers.get("Content-Type", ""),
                body=self.rfile.read(length),
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
                    max_chars=_field_int(form, "max_chars"),
                    max_tokens=_field_int(form, "max_tokens"),
                    glossary_preset=_field_value(form, "glossary_preset", ""),
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

    def _send_glossary_terms(self, job_id: str) -> None:
        try:
            job = self.engine.get_job(job_id)
            terms = self.engine.read_glossary_terms(job_id)
        except KeyError:
            self.send_error(HTTPStatus.NOT_FOUND, "job not found")
            return
        self._send_json({"job": job.to_dict(include_paths=False), "glossary_terms": terms})

    def _update_glossary_terms(self, job_id: str) -> None:
        try:
            data = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))).decode("utf-8"))
            terms = data.get("glossary_terms", data)
            if not isinstance(terms, list):
                raise ValueError("glossary_terms must be a list")
            job = self.engine.update_glossary_terms(job_id, terms)
            updated = self.engine.read_glossary_terms(job_id)
        except KeyError:
            self.send_error(HTTPStatus.NOT_FOUND, "job not found")
            return
        except (ValueError, json.JSONDecodeError) as exc:
            self.send_error(HTTPStatus.BAD_REQUEST, str(exc))
            return
        self._send_json({"job": job.to_dict(include_paths=False), "glossary_terms": updated})

    def _import_glossary_terms(self, job_id: str) -> None:
        try:
            data = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))).decode("utf-8"))
            content = str(data.get("content", ""))
            fmt = str(data.get("format", "csv"))
            default_status = str(data.get("default_status", "pending"))
            mode = str(data.get("mode", "upsert"))
            if not content.strip():
                raise ValueError("content is required")
            job, updated, summary = self.engine.import_glossary_terms(
                job_id, content, fmt=fmt, default_status=default_status, mode=mode
            )
        except KeyError:
            self.send_error(HTTPStatus.NOT_FOUND, "job not found")
            return
        except (ValueError, json.JSONDecodeError) as exc:
            self.send_error(HTTPStatus.BAD_REQUEST, str(exc))
            return
        self._send_json({"job": job.to_dict(include_paths=False), "glossary_terms": updated, "summary": summary})

    def _export_glossary_terms(self, job_id: str) -> None:
        try:
            query = parse_qs(urlparse(self.path).query)
            fmt = (query.get("format") or ["csv"])[0]
            content = self.engine.export_glossary_terms(job_id, fmt=fmt)
        except KeyError:
            self.send_error(HTTPStatus.NOT_FOUND, "job not found")
            return
        except ValueError as exc:
            self.send_error(HTTPStatus.BAD_REQUEST, str(exc))
            return
        filename = f"glossary.{_glossary_export_extension(fmt)}"
        content_type = _content_type_for_glossary_export(fmt)
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.end_headers()
        self.wfile.write(content.encode("utf-8"))

    def _update_glossary(self, job_id: str) -> None:
        try:
            content = self.rfile.read(int(self.headers.get("Content-Length", "0"))).decode("utf-8")
            job = self.engine.update_glossary(job_id, content)
        except KeyError:
            self.send_error(HTTPStatus.NOT_FOUND, "job not found")
            return
        self._send_json({"job": job.to_dict(include_paths=False), "glossary": content})

    def _autofill_glossary_terms(self, job_id: str) -> None:
        try:
            body = self.rfile.read(int(self.headers.get("Content-Length", "0"))).decode("utf-8")
            data = json.loads(body) if body.strip() else {}
            stored_settings = _read_provider_settings(self.engine.data_dir)
            merged_data = _merge_provider_settings(data, stored_settings)
            before_terms = self.engine.read_glossary_terms(job_id)
            before_empty = {
                term.get("source")
                for term in before_terms
                if term.get("status") == "pending" and not str(term.get("translation", "")).strip()
            }
            job = self.engine.autofill_glossary_terms(
                job_id,
                ProviderSettings(
                    provider=merged_data.get("provider", "openai-compatible"),
                    base_url=merged_data.get("base_url", ""),
                    api_key=merged_data.get("api_key", ""),
                    model=merged_data.get("model", ""),
                    target_language=merged_data.get("target_language", "Simplified Chinese"),
                    temperature=float(merged_data.get("temperature", 0.2)),
                    request_timeout=normalize_request_timeout(
                        merged_data.get("request_timeout", DEFAULT_REQUEST_TIMEOUT)
                    ),
                    max_retries=normalize_max_retries(merged_data.get("max_retries", DEFAULT_MAX_RETRIES)),
                    max_concurrency=normalize_max_concurrency(
                        merged_data.get("max_concurrency", DEFAULT_MAX_CONCURRENCY)
                    ),
                    structured_output_enabled=bool(merged_data.get("structured_output_enabled", False)),
                    memory_enabled=bool(merged_data.get("memory_enabled", False)),
                    memory_project_id=str(merged_data.get("memory_project_id", "")),
                    max_requests_per_minute=normalize_rate_limit(merged_data.get("max_requests_per_minute", 0)),
                    max_tokens_per_minute=normalize_rate_limit(merged_data.get("max_tokens_per_minute", 0)),
                    budget_limit=normalize_budget_limit(merged_data.get("budget_limit", 0)),
                    input_cost_per_1m_tokens=normalize_cost_per_1m(merged_data.get("input_cost_per_1m_tokens", 0)),
                    output_cost_per_1m_tokens=normalize_cost_per_1m(merged_data.get("output_cost_per_1m_tokens", 0)),
                ),
            )
            updated = self.engine.read_glossary_terms(job_id)
            filled = len(
                [
                    term
                    for term in updated
                    if term.get("source") in before_empty and str(term.get("translation", "")).strip()
                ]
            )
        except KeyError:
            self.send_error(HTTPStatus.NOT_FOUND, "job not found")
            return
        except (ValueError, json.JSONDecodeError, RuntimeError, TimeoutError, OSError) as exc:
            self.send_error(HTTPStatus.BAD_REQUEST, str(exc))
            return
        self._send_json({"job": job.to_dict(include_paths=False), "glossary_terms": updated, "filled": filled})

    def _start_job(self, job_id: str) -> None:
        try:
            data = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))).decode("utf-8"))
            stored_settings = _read_provider_settings(self.engine.data_dir)
            merged_data = _merge_provider_settings(data, stored_settings)
            job = self.engine.start_job(
                job_id,
                ProviderSettings(
                    provider=merged_data.get("provider", "openai-compatible"),
                    base_url=merged_data.get("base_url", ""),
                    api_key=merged_data.get("api_key", ""),
                    model=merged_data.get("model", ""),
                    target_language=merged_data.get("target_language", "Simplified Chinese"),
                    temperature=float(merged_data.get("temperature", 0.2)),
                    request_timeout=normalize_request_timeout(
                        merged_data.get("request_timeout", DEFAULT_REQUEST_TIMEOUT)
                    ),
                    max_retries=normalize_max_retries(merged_data.get("max_retries", DEFAULT_MAX_RETRIES)),
                    max_concurrency=normalize_max_concurrency(
                        merged_data.get("max_concurrency", DEFAULT_MAX_CONCURRENCY)
                    ),
                    structured_output_enabled=bool(merged_data.get("structured_output_enabled", False)),
                    memory_enabled=bool(merged_data.get("memory_enabled", False)),
                    memory_project_id=str(merged_data.get("memory_project_id", "")),
                    max_requests_per_minute=normalize_rate_limit(merged_data.get("max_requests_per_minute", 0)),
                    max_tokens_per_minute=normalize_rate_limit(merged_data.get("max_tokens_per_minute", 0)),
                    budget_limit=normalize_budget_limit(merged_data.get("budget_limit", 0)),
                    input_cost_per_1m_tokens=normalize_cost_per_1m(merged_data.get("input_cost_per_1m_tokens", 0)),
                    output_cost_per_1m_tokens=normalize_cost_per_1m(merged_data.get("output_cost_per_1m_tokens", 0)),
                ),
                resume=data.get("resume") is True,
                ai_qa_enabled=bool(merged_data.get("ai_qa_enabled", True)),
                auto_title_enabled=bool(merged_data.get("auto_title_enabled", False)),
            )
            _write_provider_settings(self.engine.data_dir, merged_data)
        except KeyError:
            self.send_error(HTTPStatus.NOT_FOUND, "job not found")
            return
        except (ValueError, json.JSONDecodeError) as exc:
            self.send_error(HTTPStatus.BAD_REQUEST, str(exc))
            return
        self._send_json(
            {
                "job": job.to_dict(include_paths=False),
                "provider_settings": _public_provider_settings(_read_provider_settings(self.engine.data_dir)),
            }
        )

    def _save_provider_settings(self) -> None:
        try:
            data = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))).decode("utf-8"))
            stored_settings = _read_provider_settings(self.engine.data_dir)
            merged = _merge_provider_settings(data, stored_settings)
            if merged.get("auto_title_enabled") and not (
                str(merged.get("api_key", "")).strip()
                or str(merged.get("provider", "")).lower().strip() in {"fake", "dry-run", "dry_run"}
            ):
                merged["auto_title_enabled"] = False
            _write_provider_settings(self.engine.data_dir, merged)
        except json.JSONDecodeError as exc:
            self.send_error(HTTPStatus.BAD_REQUEST, str(exc))
            return
        self._send_json({"provider_settings": _public_provider_settings(_read_provider_settings(self.engine.data_dir))})

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
            "ai-report": job.ai_quality_report_path,
        }
        artifact_path = path_map.get(artifact)
        if artifact_path is None or not artifact_path.exists():
            self.send_error(HTTPStatus.NOT_FOUND, "artifact not ready")
            return
        content_type = _content_type_for_download(artifact_path) if artifact == "output" else "text/plain; charset=utf-8"
        if artifact in {"audit", "ai-report"}:
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


def _provider_settings_path(data_dir: Path) -> Path:
    return Path(data_dir) / PROVIDER_SETTINGS_FILE


def _read_provider_settings(data_dir: Path) -> dict:
    path = _provider_settings_path(data_dir)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_provider_settings(data_dir: Path, settings: dict) -> None:
    provider = str(settings.get("provider", "openai-compatible"))
    base_url = str(settings.get("base_url", ""))
    model = str(settings.get("model", ""))
    api_key = str(settings.get("api_key", ""))
    if provider in {"fake", "dry-run", "dry_run"}:
        api_key = ""
    payload = {
        "provider": provider,
        "base_url": base_url,
        "model": model,
        "api_key": api_key,
        "max_concurrency": normalize_max_concurrency(settings.get("max_concurrency", DEFAULT_MAX_CONCURRENCY)),
        "request_timeout": normalize_request_timeout(settings.get("request_timeout", DEFAULT_REQUEST_TIMEOUT)),
        "max_retries": normalize_max_retries(settings.get("max_retries", DEFAULT_MAX_RETRIES)),
        "structured_output_enabled": bool(settings.get("structured_output_enabled", False)),
        "memory_enabled": bool(settings.get("memory_enabled", False)),
        "memory_project_id": str(settings.get("memory_project_id", "")),
        "ai_qa_enabled": bool(settings.get("ai_qa_enabled", True)),
        "auto_title_enabled": bool(settings.get("auto_title_enabled", False)),
        "max_requests_per_minute": normalize_rate_limit(settings.get("max_requests_per_minute", 0)),
        "max_tokens_per_minute": normalize_rate_limit(settings.get("max_tokens_per_minute", 0)),
        "budget_limit": normalize_budget_limit(settings.get("budget_limit", 0)),
        "input_cost_per_1m_tokens": normalize_cost_per_1m(settings.get("input_cost_per_1m_tokens", 0)),
        "output_cost_per_1m_tokens": normalize_cost_per_1m(settings.get("output_cost_per_1m_tokens", 0)),
    }
    path = _provider_settings_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def _public_provider_settings(settings: dict) -> dict:
    return {
        "provider": settings.get("provider", "openai-compatible"),
        "base_url": settings.get("base_url", ""),
        "model": settings.get("model", ""),
        "has_api_key": bool(settings.get("api_key")),
        "max_concurrency": normalize_max_concurrency(settings.get("max_concurrency", DEFAULT_MAX_CONCURRENCY)),
        "request_timeout": normalize_request_timeout(settings.get("request_timeout", DEFAULT_REQUEST_TIMEOUT)),
        "max_retries": normalize_max_retries(settings.get("max_retries", DEFAULT_MAX_RETRIES)),
        "structured_output_enabled": bool(settings.get("structured_output_enabled", False)),
        "memory_enabled": bool(settings.get("memory_enabled", False)),
        "memory_project_id": str(settings.get("memory_project_id", "")),
        "ai_qa_enabled": bool(settings.get("ai_qa_enabled", True)),
        "auto_title_enabled": bool(settings.get("auto_title_enabled", False)),
        "max_requests_per_minute": normalize_rate_limit(settings.get("max_requests_per_minute", 0)),
        "max_tokens_per_minute": normalize_rate_limit(settings.get("max_tokens_per_minute", 0)),
        "budget_limit": normalize_budget_limit(settings.get("budget_limit", 0)),
        "input_cost_per_1m_tokens": normalize_cost_per_1m(settings.get("input_cost_per_1m_tokens", 0)),
        "output_cost_per_1m_tokens": normalize_cost_per_1m(settings.get("output_cost_per_1m_tokens", 0)),
    }


def _merge_provider_settings(data: dict, stored: dict) -> dict:
    merged = dict(data)
    provider = str(merged.get("provider") or stored.get("provider") or "openai-compatible")
    base_url = str(merged.get("base_url") or stored.get("base_url") or "")
    stored_provider = str(stored.get("provider") or "")
    stored_base_url = str(stored.get("base_url") or "")
    same_secret_scope = provider == stored_provider and base_url == stored_base_url
    if not str(merged.get("api_key") or "").strip() and same_secret_scope:
        merged["api_key"] = stored.get("api_key", "")
    for key in (
        "provider",
        "base_url",
        "model",
        "max_concurrency",
        "request_timeout",
        "max_retries",
        "structured_output_enabled",
        "memory_enabled",
        "memory_project_id",
        "ai_qa_enabled",
        "auto_title_enabled",
        "max_requests_per_minute",
        "max_tokens_per_minute",
        "budget_limit",
        "input_cost_per_1m_tokens",
        "output_cost_per_1m_tokens",
    ):
        if merged.get(key) in (None, "") and stored.get(key) not in (None, ""):
            merged[key] = stored[key]
    merged["provider"] = provider
    merged["base_url"] = base_url
    return merged


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
    if not boundary:
        raise ValueError("multipart boundary missing")
    delimiter = b"--" + boundary
    if delimiter not in body:
        raise ValueError("multipart body does not contain boundary")
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
    if not parts:
        raise ValueError("multipart body contains no form parts")
    return parts


def _max_upload_bytes() -> int:
    raw_value = os.environ.get("BABEL_MAX_UPLOAD_MB", str(DEFAULT_MAX_UPLOAD_MB))
    try:
        megabytes = int(raw_value)
    except ValueError:
        megabytes = DEFAULT_MAX_UPLOAD_MB
    megabytes = max(1, megabytes)
    return megabytes * 1024 * 1024


def _field_value(form: dict[str, FormPart], name: str, default: str) -> str:
    part = form.get(name)
    if part is None:
        return default
    return part.value if part.value else default


def _field_int(form: dict[str, FormPart], name: str) -> int | None:
    value = _field_value(form, name, "").strip()
    if not value:
        return None
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be a positive integer") from exc
    if parsed <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return parsed


def _glossary_export_extension(fmt: str) -> str:
    value = fmt.lower().strip()
    if value in {"md", "markdown", "preset"}:
        return "md"
    if value in {"tbx", "xml"}:
        return "tbx"
    if value == "json":
        return "json"
    return "csv"


def _content_type_for_glossary_export(fmt: str) -> str:
    ext = _glossary_export_extension(fmt)
    if ext == "csv":
        return "text/csv; charset=utf-8"
    if ext == "tbx":
        return "application/xml; charset=utf-8"
    if ext == "json":
        return "application/json; charset=utf-8"
    return "text/markdown; charset=utf-8"


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


def _package_version() -> str:
    try:
        return metadata.version("babel-epub")
    except metadata.PackageNotFoundError:
        return __version__


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
