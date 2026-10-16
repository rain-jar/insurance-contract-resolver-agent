from __future__ import annotations

import hashlib
import io
import json
import re
import shutil
import subprocess
from pathlib import Path

import pdfplumber
from bs4 import BeautifulSoup

from .models import ExtractionMethod, TextBlock


class IngestionError(RuntimeError):
    pass


class DocumentIngestor:
    CACHE_VERSION = "ingestion-v1"

    def __init__(self, cache_dir: Path | None = None, ocr_dpi: int = 144) -> None:
        self.cache_dir = cache_dir
        self.ocr_dpi = ocr_dpi

    def ingest(self, path: Path, display_path: str | None = None) -> list[TextBlock]:
        display_path = display_path or path.as_posix()
        cached = self._read_cache(path)
        if cached is not None:
            return [TextBlock.model_validate(item) for item in cached]

        suffix = path.suffix.lower()
        if suffix == ".txt":
            blocks = self._ingest_txt(path, display_path)
        elif suffix in {".html", ".htm"}:
            blocks = self._ingest_html(path, display_path)
        elif suffix == ".pdf":
            blocks = self._ingest_pdf(path, display_path)
        else:
            raise IngestionError(f"Unsupported document format: {path.suffix}")

        self._write_cache(path, blocks)
        return blocks

    def _ingest_txt(self, path: Path, display_path: str) -> list[TextBlock]:
        text = path.read_text(encoding="utf-8")
        paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
        return [
            TextBlock(
                document_path=display_path,
                block_index=index,
                locator=f"paragraph:{index + 1}",
                text=paragraph,
                extraction_method=ExtractionMethod.TEXT,
                page_number=None,
            )
            for index, paragraph in enumerate(paragraphs)
        ]

    def _ingest_html(self, path: Path, display_path: str) -> list[TextBlock]:
        soup = BeautifulSoup(path.read_text(encoding="utf-8", errors="replace"), "html.parser")
        for element in soup(["script", "style"]):
            element.decompose()

        blocks: list[TextBlock] = []
        tags = soup.find_all(["h1", "h2", "h3", "h4", "p", "tr"])
        for tag in tags:
            if tag.name == "p" and tag.find_parent("tr") is not None:
                continue
            text = " ".join(tag.get_text(" ", strip=True).split())
            if not text:
                continue
            index = len(blocks)
            blocks.append(
                TextBlock(
                    document_path=display_path,
                    block_index=index,
                    locator=f"html:{tag.name}:{index + 1}",
                    text=text,
                    extraction_method=ExtractionMethod.HTML,
                    page_number=None,
                )
            )
        if not blocks:
            raise IngestionError(f"No visible text extracted from HTML: {path}")
        return blocks

    def _ingest_pdf(self, path: Path, display_path: str) -> list[TextBlock]:
        blocks: list[TextBlock] = []
        with pdfplumber.open(path) as pdf:
            for index, page in enumerate(pdf.pages):
                text = page.extract_text(x_tolerance=2, y_tolerance=3, layout=True) or ""
                method = ExtractionMethod.TEXT
                if not is_usable_pdf_text(text):
                    text = self._ocr_page(page, path, index + 1)
                    method = ExtractionMethod.OCR
                text = text.strip()
                if not text:
                    raise IngestionError(f"No text extracted from {path}, page {index + 1}")
                blocks.append(
                    TextBlock(
                        document_path=display_path,
                        block_index=index,
                        locator=f"page:{index + 1}",
                        text=text,
                        extraction_method=method,
                        page_number=index + 1,
                    )
                )
        return blocks

    def _ocr_page(self, page: pdfplumber.page.Page, path: Path, page_number: int) -> str:
        if shutil.which("tesseract") is None:
            raise IngestionError(
                f"Page {page_number} of {path} needs OCR, but the tesseract executable is unavailable"
            )
        image = page.to_image(resolution=self.ocr_dpi, antialias=True).original
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        completed = subprocess.run(
            ["tesseract", "stdin", "stdout", "--psm", "6"],
            input=buffer.getvalue(),
            capture_output=True,
            check=False,
        )
        if completed.returncode != 0:
            detail = completed.stderr.decode("utf-8", errors="replace").strip()
            raise IngestionError(f"OCR failed for {path}, page {page_number}: {detail}")
        return completed.stdout.decode("utf-8", errors="replace")

    def _cache_path(self, path: Path) -> Path | None:
        if self.cache_dir is None:
            return None
        digest_input = (
            f"{self.CACHE_VERSION}\0ocr_dpi={self.ocr_dpi}\0{path.resolve()}\0".encode("utf-8")
            + path.read_bytes()
        )
        digest = hashlib.sha256(digest_input).hexdigest()
        return self.cache_dir / f"{digest}.json"

    def _read_cache(self, path: Path) -> list[dict[str, object]] | None:
        cache_path = self._cache_path(path)
        if cache_path is None or not cache_path.exists():
            return None
        return json.loads(cache_path.read_text(encoding="utf-8"))

    def _write_cache(self, path: Path, blocks: list[TextBlock]) -> None:
        cache_path = self._cache_path(path)
        if cache_path is None:
            return
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(
            json.dumps([block.model_dump(mode="json") for block in blocks], indent=2),
            encoding="utf-8",
        )


def is_usable_pdf_text(text: str) -> bool:
    normalized = text.strip()
    if len(re.findall(r"[A-Za-z0-9]", normalized)) < 50:
        return False
    if normalized.count("(cid:") >= 5:
        return False
    return True
