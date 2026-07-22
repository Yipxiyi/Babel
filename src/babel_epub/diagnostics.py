"""User-facing, actionable diagnostics shared by every Babel input format."""

from __future__ import annotations

import re
from pathlib import Path


def diagnose_error(
    error: Exception | str,
    *,
    stage: str,
    filename: str = "",
    input_format: str = "",
    batch: dict | None = None,
) -> dict:
    detail = str(error).strip() or "Unknown error"
    lowered = detail.lower()
    code = "unexpected-error"
    owner = "unknown"
    title = "Babel could not complete this step"
    message = detail
    guidance = [
        "Retry once with adaptive processing enabled.",
        "If the problem continues, share the technical details with the project maintainer or an agent.",
    ]
    retryable = False

    if "upload exceeds configured limit" in lowered or "request entity too large" in lowered:
        code, owner, title = "upload-too-large", "source_file", "The uploaded file is larger than this server allows"
        message = "Babel stopped before processing the file, so no provider request was made."
        guidance = [
            "Compress image-heavy source files or use a smaller source copy.",
            "A server administrator can raise BABEL_MAX_UPLOAD_MB when enough disk and memory are available.",
        ]
    elif "requires calibre" in lowered or "ebook-convert" in lowered and "not found" in lowered:
        code, owner, title = "converter-unavailable", "environment", "This format needs a converter that is not installed"
        message = "Babel cannot normalize this source format in the current environment."
        guidance = ["Use the Babel Docker image, install Calibre, or upload an EPUB version of the book."]
    elif "ebook-convert timed out" in lowered:
        code, owner, title = "conversion-timeout", "source_file", "The source file took too long to convert"
        message = "The file may be unusually complex, image-heavy, damaged, or scanned."
        guidance = [
            "Check whether the document opens normally and is not password-protected.",
            "For scanned PDFs, run OCR or create a text-based PDF before retrying.",
            "An administrator can increase BABEL_CONVERSION_TIMEOUT for a valid but slow file.",
        ]
        retryable = True
    elif "bad zip" in lowered or "not a zip file" in lowered or "path traversal" in lowered or "encrypted" in lowered:
        code, owner, title = "invalid-source-file", "source_file", "The source file is damaged, encrypted, or unsafe"
        message = "Babel could not safely open the uploaded document."
        guidance = ["Open and re-export the source file, remove password protection, then upload the new copy."]
    elif "no translatable" in lowered or "0 translatable" in lowered:
        code, owner, title = "no-text-detected", "source_file", "No translatable text was found"
        message = "The document may be image-only, scanned, or structured in a way Babel cannot read yet."
        guidance = ["Run OCR for scanned documents, then retry with the resulting searchable PDF or EPUB."]
    elif re.search(r"provider http\s+(401|403)", lowered) or "api key" in lowered or "unauthorized" in lowered:
        code, owner, title = "provider-authentication", "api", "The translation API rejected the credentials"
        message = "The source file is intact, but Babel could not authenticate with the configured provider."
        guidance = ["Check the API key, Base URL, provider selection, account access, and model name in Settings."]
    elif "provider http 429" in lowered or "rate limit" in lowered:
        code, owner, title = "provider-rate-limit", "api", "The translation API is rate-limiting this job"
        message = "The provider received too many requests or the account quota is temporarily exhausted."
        guidance = [
            "Wait briefly and continue the job; completed batches will be kept.",
            "Use adaptive processing or lower concurrency in Advanced Settings.",
            "Check the provider account quota and billing status.",
        ]
        retryable = True
    elif "timed out" in lowered or "timeout" in lowered:
        code, owner, title = "provider-timeout", "api", "The translation API did not finish this batch in time"
        message = "Babel will automatically split eligible batches into smaller requests before giving up."
        guidance = [
            "Continue the job after checking that the provider is reachable.",
            "For local models, keep adaptive processing enabled so Babel reduces concurrency automatically.",
        ]
        retryable = True
    elif (
        "context" in lowered and ("length" in lowered or "large" in lowered or "token" in lowered)
    ) or "request too large" in lowered:
        code, owner, title = "provider-context-limit", "api", "This batch is larger than the model can accept"
        message = "The source file is readable, but the configured model has a smaller context window."
        guidance = [
            "Keep adaptive processing enabled so Babel can split the batch.",
            "If using Custom mode, reduce the batch character limit in Advanced Settings.",
        ]
        retryable = True
    elif "provider http" in lowered or "unexpected openai" in lowered or "unexpected anthropic" in lowered:
        code, owner, title = "provider-error", "api", "The translation API returned an error"
        message = "Babel reached the provider, but the provider could not complete the request."
        guidance = ["Check provider status, model availability, quota, and the technical details below before continuing."]
        retryable = bool(re.search(r"provider http\s+5\d\d", lowered))
    elif "validation" in lowered or "invalid json" in lowered or "missing translated row" in lowered:
        code, owner, title = "invalid-provider-output", "api", "The model response did not pass Babel's validation"
        message = "Babel rejected the output to protect the book's structure and prevent incomplete translations."
        guidance = [
            "Continue with adaptive processing enabled; Babel will retry smaller requests where possible.",
            "Enable Structured JSON output when the configured provider supports it.",
        ]
        retryable = True
    elif stage in {"package", "audit"}:
        code, owner, title = "output-build-failed", "babel", "Babel could not build the final book"
        message = "Translation output exists, but final validation or packaging did not complete."
        guidance = ["Keep the job data and ask an agent or maintainer to inspect the audit and technical details."]

    return {
        "code": code,
        "stage": stage,
        "owner": owner,
        "title": title,
        "message": message,
        "guidance": guidance,
        "retryable": retryable,
        "technical_detail": detail,
        "filename": Path(filename).name if filename else "",
        "input_format": input_format,
        "batch": batch or None,
    }


__all__ = ["diagnose_error"]
