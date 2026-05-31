"""Dependency-free self-hosted Web UI for Babel."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from .jobs import BabelJobEngine, JobRequest
from .providers import ProviderSettings


INDEX_HTML = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Babel · EPUB Translation</title>
  <style>
    :root{--paper:#f6f1e7;--ink:#17130f;--clay:#c86f37;--muted:#776b5e;--line:#dacfbf;--panel:#fffaf0}
    *{box-sizing:border-box} body{margin:0;background:radial-gradient(circle at top left,#fffaf0,var(--paper));color:var(--ink);font:15px/1.45 Georgia,"Times New Roman",serif}
    header{display:flex;align-items:center;justify-content:space-between;padding:28px 34px;border-bottom:1px solid var(--line)}
    .brand{display:flex;gap:14px;align-items:center}.mark{width:46px;height:46px;border-radius:14px;background:var(--ink);position:relative}.mark:before,.mark:after{content:"";position:absolute;left:10px;right:10px;border-top:5px solid var(--paper);border-radius:10px}.mark:before{top:15px}.mark:after{top:27px}
    h1{font-size:31px;line-height:1;margin:0;letter-spacing:-.04em}.tagline{color:var(--muted);font-size:14px;margin-top:4px}
    main{display:grid;grid-template-columns:340px minmax(360px,1fr) 320px;gap:18px;padding:22px}
    section{background:rgba(255,250,240,.82);border:1px solid var(--line);border-radius:24px;padding:20px;box-shadow:0 18px 50px rgba(23,19,15,.08)}
    h2{font-size:18px;margin:0 0 14px;letter-spacing:-.02em}.field{margin:13px 0}label{display:block;font:12px/1.2 ui-monospace,SFMono-Regular,Menlo,monospace;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);margin-bottom:7px}
    input,select,textarea,button{width:100%;border:1px solid var(--line);border-radius:14px;padding:11px 12px;background:#fffdf7;color:var(--ink);font:14px/1.35 ui-sans-serif,system-ui,sans-serif}
    textarea{min-height:290px;resize:vertical;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12px}
    button{cursor:pointer;background:var(--ink);color:var(--paper);border-color:var(--ink);font-weight:700}button.secondary{background:#fffdf7;color:var(--ink);border-color:var(--line)}button:disabled{opacity:.5;cursor:not-allowed}
    .status{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;background:#17130f;color:#f6f1e7;border-radius:18px;padding:16px;min-height:160px;white-space:pre-wrap;overflow:auto}.progress{height:12px;background:#eadfce;border-radius:99px;overflow:hidden}.bar{height:100%;width:0;background:var(--clay);transition:width .25s ease}
    a.download{display:block;margin:10px 0;padding:12px;border:1px solid var(--line);border-radius:14px;color:var(--ink);text-decoration:none;background:#fffdf7;font-family:ui-sans-serif,system-ui,sans-serif}
    .hint{color:var(--muted);font-size:13px}.row{display:grid;grid-template-columns:1fr 1fr;gap:10px}
    @media (max-width: 1040px){main{grid-template-columns:1fr}header{align-items:flex-start;gap:12px;flex-direction:column}}
  </style>
</head>
<body>
  <header>
    <div class="brand"><div class="mark"></div><div><h1>Babel</h1><div class="tagline">Preserve XHTML. Translate in batches. Rebuild clean.</div></div></div>
    <div class="hint">Self-hosted EPUB translation workspace</div>
  </header>
  <main>
    <section>
      <h2>Upload EPUB</h2>
      <form id="uploadForm">
        <div class="field"><label>EPUB file</label><input required name="epub" type="file" accept=".epub,application/epub+zip"></div>
        <div class="field"><label>Target Language</label><input name="target_language" value="Simplified Chinese"></div>
        <div class="row">
          <div class="field"><label>Output Title</label><input name="title" placeholder="Translated title"></div>
          <div class="field"><label>Language Code</label><input name="language" value="zh-CN"></div>
        </div>
        <button type="submit">Prepare Workspace</button>
      </form>
      <hr>
      <h2>API Provider</h2>
      <div class="field"><label>Provider</label><select id="provider"><option value="openai-compatible">OpenAI Compatible</option><option value="anthropic">Anthropic Claude</option><option value="fake">Fake Dry Run</option></select></div>
      <div class="field"><label>Base URL</label><input id="baseUrl" value="https://api.openai.com/v1"></div>
      <div class="field"><label>API Key</label><input id="apiKey" type="password" autocomplete="off"></div>
      <div class="field"><label>Model</label><input id="model" value="gpt-4.1"></div>
      <button id="startBtn" disabled>Start Translation</button>
      <p class="hint">Keys are sent only to this local server process. Do not expose this app publicly without adding auth.</p>
    </section>
    <section>
      <h2>Glossary</h2>
      <textarea id="glossary" placeholder="Prepare a job to review glossary candidates."></textarea>
      <button class="secondary" id="saveGlossary" disabled>Save Glossary</button>
      <h2 style="margin-top:20px">Job Progress</h2>
      <div class="progress"><div class="bar" id="bar"></div></div>
      <pre class="status" id="status">No job prepared.</pre>
    </section>
    <section>
      <h2>Downloads</h2>
      <a class="download" id="downloadEpub" href="#" hidden>Download EPUB</a>
      <a class="download" id="downloadGlossary" href="#" hidden>Download Glossary</a>
      <a class="download" id="downloadReport" href="#" hidden>Download Report</a>
      <a class="download" id="downloadAudit" href="#" hidden>Download Audit JSON</a>
      <h2 style="margin-top:20px">Validation</h2>
      <p class="hint">Babel validates batch row IDs, root tags, structural attributes, links, anchors, placeholder text, ZIP integrity, and EPUB internal references before exposing downloads.</p>
    </section>
  </main>
<script>
let currentJob = null; let pollTimer = null;
const statusEl = document.getElementById('status'); const glossaryEl = document.getElementById('glossary');
function showStatus(job){ const pct = job.total_batches ? Math.round(job.completed_batches / job.total_batches * 100) : 0; document.getElementById('bar').style.width = pct + '%'; statusEl.textContent = JSON.stringify({id:job.job_id,status:job.status,message:job.message,batches:`${job.completed_batches}/${job.total_batches}`,errors:job.errors}, null, 2); const done = job.status === 'completed'; const id=job.job_id; for (const [el,path] of [['downloadEpub','output'],['downloadGlossary','glossary'],['downloadReport','report'],['downloadAudit','audit']]){ const a=document.getElementById(el); a.hidden = !done && path !== 'glossary'; a.href = `/api/jobs/${id}/download/${path}`; } }
async function refresh(){ if(!currentJob) return; const res = await fetch(`/api/jobs/${currentJob}`); const data = await res.json(); showStatus(data.job); if(data.glossary && document.activeElement !== glossaryEl) glossaryEl.value = data.glossary; if(['completed','failed'].includes(data.job.status) && pollTimer){ clearInterval(pollTimer); pollTimer = null; } }
document.getElementById('uploadForm').addEventListener('submit', async (e)=>{ e.preventDefault(); const form=new FormData(e.target); const res=await fetch('/api/jobs',{method:'POST',body:form}); const data=await res.json(); currentJob=data.job.job_id; document.getElementById('startBtn').disabled=false; document.getElementById('saveGlossary').disabled=false; showStatus(data.job); glossaryEl.value=data.glossary; });
document.getElementById('saveGlossary').addEventListener('click', async ()=>{ await fetch(`/api/jobs/${currentJob}/glossary`,{method:'POST',body:glossaryEl.value}); await refresh(); });
document.getElementById('startBtn').addEventListener('click', async ()=>{ const payload={provider:provider.value,base_url:baseUrl.value,api_key:apiKey.value,model:model.value,target_language:document.querySelector('[name=target_language]').value}; const res=await fetch(`/api/jobs/${currentJob}/start`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)}); const data=await res.json(); showStatus(data.job); pollTimer=setInterval(refresh,1500); });
</script>
</body>
</html>"""


def render_index_html() -> str:
    return INDEX_HTML


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
        if path == "/":
            self._send_bytes(render_index_html().encode("utf-8"), "text/html; charset=utf-8")
            return
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
        job = self.engine.create_job(
            JobRequest(
                filename=filename,
                content=file_item.content,
                target_language=_field_value(form, "target_language", "Simplified Chinese"),
                title=_field_value(form, "title", ""),
                language=_field_value(form, "language", "zh-CN"),
            )
        )
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
                ),
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
            "output": job.output_epub,
            "glossary": job.glossary_path,
            "report": job.report_path,
            "audit": job.audit_path,
        }
        artifact_path = path_map.get(artifact)
        if artifact_path is None or not artifact_path.exists():
            self.send_error(HTTPStatus.NOT_FOUND, "artifact not ready")
            return
        content_type = "application/epub+zip" if artifact == "output" else "text/plain; charset=utf-8"
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
