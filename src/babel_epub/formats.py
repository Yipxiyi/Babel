"""Input ebook format detection and EPUB normalization."""

from __future__ import annotations

import html
import json
import re
import shutil
import subprocess
import zipfile
from dataclasses import dataclass
from pathlib import Path


class BookFormatError(ValueError):
    """Raised when Babel cannot convert an input or output book format."""


DIRECT_EPUB = {".epub"}
INTERNAL_CONVERSION = {".txt", ".html", ".htm", ".xhtml"}
CALIBRE_CONVERSION = {
    ".azw",
    ".azw3",
    ".azw4",
    ".cb7",
    ".cba",
    ".cbr",
    ".cbt",
    ".cbz",
    ".chm",
    ".docx",
    ".fb2",
    ".htmlz",
    ".kfx",
    ".lit",
    ".lrf",
    ".mobi",
    ".odt",
    ".pdb",
    ".pdf",
    ".pml",
    ".prc",
    ".rb",
    ".rtf",
    ".snb",
    ".tcr",
}
NATIVE_OUTPUT = {".epub"}
CALIBRE_OUTPUT = {
    ".azw3",
    ".docx",
    ".fb2",
    ".html",
    ".htmlz",
    ".kepub",
    ".mobi",
    ".pdf",
    ".rtf",
    ".txt",
}


@dataclass(frozen=True)
class InputFormat:
    extension: str
    label: str
    conversion: str

    def to_epub(
        self,
        input_path: Path,
        output_epub: Path,
        converter_path: str | None = None,
    ) -> dict:
        output_epub.parent.mkdir(parents=True, exist_ok=True)
        if self.conversion == "native":
            shutil.copy2(input_path, output_epub)
            return self.metadata(input_path, output_epub, "copied")
        if self.conversion == "internal-text":
            create_text_epub(input_path, output_epub)
            return self.metadata(input_path, output_epub, "internal-text")
        if self.conversion == "internal-html":
            create_html_epub(input_path, output_epub)
            return self.metadata(input_path, output_epub, "internal-html")
        if self.conversion == "calibre":
            command = resolve_ebook_convert(converter_path)
            if not command:
                raise BookFormatError(
                    f"{self.extension} input requires Calibre `ebook-convert`. "
                    "Install Calibre or convert the book to EPUB before using Babel."
                )
            run_calibre_conversion(command, input_path, output_epub)
            return self.metadata(input_path, output_epub, "calibre")
        raise BookFormatError(f"unsupported conversion path for {self.extension}")

    def metadata(self, input_path: Path, output_epub: Path, method: str) -> dict:
        return {
            "input_file": input_path.name,
            "input_format": self.extension,
            "format_label": self.label,
            "conversion_method": method,
            "normalized_epub": output_epub.name,
        }


def supported_input_extensions() -> list[str]:
    return sorted(DIRECT_EPUB | INTERNAL_CONVERSION | CALIBRE_CONVERSION)


def supported_output_extensions() -> list[str]:
    return sorted(NATIVE_OUTPUT | CALIBRE_OUTPUT)


def detect_input_format(path: Path) -> InputFormat:
    extension = path.suffix.lower()
    if extension in DIRECT_EPUB:
        return InputFormat(extension=extension, label="EPUB", conversion="native")
    if extension == ".txt":
        return InputFormat(extension=extension, label="Plain text", conversion="internal-text")
    if extension in {".html", ".htm", ".xhtml"}:
        return InputFormat(extension=extension, label="HTML", conversion="internal-html")
    if extension in CALIBRE_CONVERSION:
        return InputFormat(extension=extension, label=extension.lstrip(".").upper(), conversion="calibre")
    raise BookFormatError(
        f"unsupported input format: {extension or '(no extension)'}. "
        f"Supported: {', '.join(supported_input_extensions())}"
    )


def normalize_to_epub(input_path: Path, work_dir: Path, converter_path: str | None = None) -> dict:
    if not input_path.exists():
        raise FileNotFoundError(input_path)
    input_format = detect_input_format(input_path)
    original_path = work_dir / f"input_original{input_format.extension}"
    epub_path = work_dir / "input.epub"
    original_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(input_path, original_path)
    metadata = input_format.to_epub(original_path, epub_path, converter_path=converter_path)
    metadata["original_path"] = original_path.name
    return metadata


def normalize_extension(value: str | None, fallback: str = ".epub") -> str:
    extension = (value or fallback).strip().lower()
    if not extension:
        extension = fallback
    if not extension.startswith("."):
        extension = f".{extension}"
    return extension


def resolve_ebook_convert(converter_path: str | None = None) -> str | None:
    if converter_path:
        candidate = Path(converter_path)
        if candidate.exists():
            return str(candidate)
        return shutil.which(converter_path)
    return shutil.which("ebook-convert")


def convert_epub_to_output(
    source_epub: Path,
    output_path: Path,
    output_format: str | None = None,
    converter_path: str | None = None,
) -> dict:
    if not source_epub.exists():
        raise FileNotFoundError(source_epub)
    extension = normalize_extension(output_format or output_path.suffix or ".epub")
    if extension not in supported_output_extensions():
        raise BookFormatError(
            f"unsupported output format: {extension}. Supported: {', '.join(supported_output_extensions())}"
        )
    output_suffix = output_path.suffix.lower()
    if not output_suffix:
        raise BookFormatError(f"output path must include the selected output extension {extension}")
    if output_suffix and output_suffix != extension:
        raise BookFormatError(
            f"output path suffix {output_suffix} does not match selected output format {extension}"
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if extension in NATIVE_OUTPUT:
        if source_epub.resolve() != output_path.resolve():
            shutil.copy2(source_epub, output_path)
        return output_metadata(output_path, extension, "copied")

    command = resolve_ebook_convert(converter_path)
    if not command:
        raise BookFormatError(
            f"{extension} output requires Calibre `ebook-convert`. "
            "Install Calibre or choose EPUB output."
        )
    run_calibre_conversion(command, source_epub, output_path)
    return output_metadata(output_path, extension, "calibre")


def output_metadata(output_path: Path, extension: str, method: str) -> dict:
    return {
        "output_file": output_path.name,
        "output_format": extension,
        "output_conversion_method": method,
    }


def run_calibre_conversion(command: str, input_path: Path, output_epub: Path) -> None:
    result = subprocess.run(
        [command, str(input_path), str(output_epub)],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise BookFormatError(f"ebook-convert failed for {input_path.name}: {detail}")


def create_text_epub(input_path: Path, output_epub: Path) -> None:
    text = input_path.read_text(encoding="utf-8", errors="replace")
    paragraphs = [paragraph.strip() for paragraph in re.split(r"\n\s*\n", text) if paragraph.strip()]
    title = paragraphs[0][:80] if paragraphs else input_path.stem
    body = "\n".join(f"<p>{html.escape(paragraph)}</p>" for paragraph in paragraphs)
    create_minimal_epub(title=title, body_xhtml=body, output_epub=output_epub)


def create_html_epub(input_path: Path, output_epub: Path) -> None:
    raw = input_path.read_text(encoding="utf-8", errors="replace")
    title_match = re.search(r"<title[^>]*>(.*?)</title>", raw, flags=re.IGNORECASE | re.DOTALL)
    h1_match = re.search(r"<h1[^>]*>(.*?)</h1>", raw, flags=re.IGNORECASE | re.DOTALL)
    title = _strip_tags(title_match.group(1) if title_match else h1_match.group(1) if h1_match else input_path.stem)
    body_match = re.search(r"<body[^>]*>(.*?)</body>", raw, flags=re.IGNORECASE | re.DOTALL)
    body = body_match.group(1) if body_match else raw
    body = _sanitize_html_fragment(body)
    create_minimal_epub(title=title or input_path.stem, body_xhtml=body, output_epub=output_epub)


def _strip_tags(value: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", value)).strip()


def _sanitize_html_fragment(value: str) -> str:
    fragment = re.sub(r"(?is)<script[^>]*>.*?</script>", "", value)
    fragment = re.sub(r"(?is)<style[^>]*>.*?</style>", "", fragment)
    fragment = re.sub(r"(?is)<!doctype[^>]*>", "", fragment)
    fragment = re.sub(r"(?is)</?(?:html|head|body|meta|title|link)[^>]*>", "", fragment)
    if not re.search(r"<(?:p|h[1-6]|blockquote|ul|ol|li)\b", fragment, flags=re.IGNORECASE):
        fragment = f"<p>{html.escape(_strip_tags(fragment))}</p>"
    return fragment.strip()


def create_minimal_epub(title: str, body_xhtml: str, output_epub: Path) -> None:
    output_epub.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output_epub, "w") as archive:
        archive.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        archive.writestr(
            "META-INF/container.xml",
            """<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
""",
            compress_type=zipfile.ZIP_DEFLATED,
        )
        archive.writestr(
            "OEBPS/content.opf",
            f"""<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="2.0" unique-identifier="bookid">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>{html.escape(title)}</dc:title>
    <dc:language>en</dc:language>
    <dc:identifier id="bookid">babel-generated</dc:identifier>
  </metadata>
  <manifest>
    <item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>
    <item id="chapter1" href="chapter1.xhtml" media-type="application/xhtml+xml"/>
    <item id="style" href="style.css" media-type="text/css"/>
  </manifest>
  <spine toc="ncx">
    <itemref idref="chapter1"/>
  </spine>
</package>
""",
            compress_type=zipfile.ZIP_DEFLATED,
        )
        archive.writestr("OEBPS/style.css", "body { line-height: 1.5; }\n", compress_type=zipfile.ZIP_DEFLATED)
        archive.writestr(
            "OEBPS/toc.ncx",
            f"""<?xml version="1.0" encoding="utf-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
  <head><meta name="dtb:uid" content="babel-generated"/></head>
  <docTitle><text>{html.escape(title)}</text></docTitle>
  <navMap>
    <navPoint id="nav1" playOrder="1">
      <navLabel><text>{html.escape(title)}</text></navLabel>
      <content src="chapter1.xhtml"/>
    </navPoint>
  </navMap>
</ncx>
""",
            compress_type=zipfile.ZIP_DEFLATED,
        )
        archive.writestr(
            "OEBPS/chapter1.xhtml",
            f"""<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
  <head><title>{html.escape(title)}</title><link rel="stylesheet" href="style.css"/></head>
  <body>
    {body_xhtml}
  </body>
</html>
""",
            compress_type=zipfile.ZIP_DEFLATED,
        )


def write_input_format_metadata(pipeline_dir: Path, metadata: dict) -> None:
    (pipeline_dir / "input_format.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def write_output_format_metadata(pipeline_dir: Path, metadata: dict) -> None:
    (pipeline_dir / "output_format.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
