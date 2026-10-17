from __future__ import annotations

import hashlib
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO
from uuid import UUID

from .application import AnalysisLimits, SUPPORTED_DOCUMENT_SUFFIXES


class DocumentStorageError(ValueError):
    pass


@dataclass(frozen=True)
class UploadSource:
    filename: str
    stream: BinaryIO


@dataclass(frozen=True)
class StoredDocument:
    display_name: str
    relative_path: str
    byte_size: int
    sha256: str


class LocalDocumentStore:
    """Controlled local storage for originals and stack-scoped derived caches."""

    def __init__(self, root: Path, limits: AnalysisLimits | None = None) -> None:
        self.root = root.resolve()
        self.limits = limits or AnalysisLimits()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.incoming_root = self.root / ".incoming"
        self.incoming_root.mkdir(exist_ok=True, mode=0o700)

    def save_stack(
        self, stack_id: str, uploads: list[UploadSource]
    ) -> list[StoredDocument]:
        stack_id = _validated_id(stack_id)
        if not uploads:
            raise DocumentStorageError("At least one contract document is required.")
        if len(uploads) > self.limits.max_documents:
            raise DocumentStorageError(
                f"A contract stack may contain at most {self.limits.max_documents} documents."
            )

        final_path = self._stack_path(stack_id)
        incoming_path = self.incoming_root / stack_id
        if final_path.exists() or incoming_path.exists():
            raise DocumentStorageError("The stack storage location already exists.")
        documents_path = incoming_path / "documents"
        documents_path.mkdir(parents=True, mode=0o700)

        stored: list[StoredDocument] = []
        names: set[str] = set()
        total_bytes = 0
        try:
            for upload in uploads:
                filename = _validated_filename(upload.filename)
                canonical_name = filename.casefold()
                if canonical_name in names:
                    raise DocumentStorageError(f"Duplicate document name: {filename}")
                names.add(canonical_name)

                destination = documents_path / filename
                byte_size, digest = self._copy_bounded(upload.stream, destination)
                total_bytes += byte_size
                if total_bytes > self.limits.max_stack_bytes:
                    raise DocumentStorageError(
                        f"Contract stack exceeds the {self.limits.max_stack_bytes}-byte limit."
                    )
                stored.append(
                    StoredDocument(
                        display_name=filename,
                        relative_path=f"documents/{filename}",
                        byte_size=byte_size,
                        sha256=digest,
                    )
                )
            incoming_path.replace(final_path)
        except Exception:
            if incoming_path.exists():
                shutil.rmtree(incoming_path)
            raise
        return stored

    def stack_path(self, stack_id: str) -> Path:
        return self._stack_path(_validated_id(stack_id))

    def document_path(self, stack_id: str, relative_path: str) -> Path:
        stack_path = self.stack_path(stack_id)
        candidate = (stack_path / relative_path).resolve()
        if not candidate.is_relative_to(stack_path):
            raise DocumentStorageError("Stored document path escapes its contract stack.")
        return candidate

    def ingestion_cache_path(self, stack_id: str) -> Path:
        path = self.stack_path(stack_id) / "derived" / "ingestion"
        path.mkdir(parents=True, exist_ok=True, mode=0o700)
        return path

    def embedding_cache_path(self, stack_id: str) -> Path:
        path = self.stack_path(stack_id) / "derived" / "embeddings"
        path.mkdir(parents=True, exist_ok=True, mode=0o700)
        return path

    def delete_stack(self, stack_id: str) -> None:
        target = self._stack_path(_validated_id(stack_id))
        if target.exists():
            shutil.rmtree(target)

    def _stack_path(self, stack_id: str) -> Path:
        candidate = (self.root / stack_id).resolve()
        if candidate.parent != self.root:
            raise DocumentStorageError("Invalid stack storage path.")
        return candidate

    def _copy_bounded(self, source: BinaryIO, destination: Path) -> tuple[int, str]:
        digest = hashlib.sha256()
        byte_size = 0
        with destination.open("xb") as output:
            while block := source.read(1024 * 1024):
                byte_size += len(block)
                if byte_size > self.limits.max_document_bytes:
                    raise DocumentStorageError(
                        f"Document exceeds the {self.limits.max_document_bytes}-byte limit: "
                        f"{destination.name}"
                    )
                output.write(block)
                digest.update(block)
        if byte_size == 0:
            raise DocumentStorageError(f"Document is empty: {destination.name}")
        return byte_size, digest.hexdigest()


def _validated_id(value: str) -> str:
    try:
        parsed = UUID(value)
    except ValueError as exc:
        raise DocumentStorageError("Invalid stack identifier.") from exc
    if str(parsed) != value:
        raise DocumentStorageError("Invalid stack identifier.")
    return value


def _validated_filename(value: str) -> str:
    filename = value.strip()
    if (
        not filename
        or filename in {".", ".."}
        or Path(filename).name != filename
        or "/" in filename
        or "\\" in filename
        or "\x00" in filename
    ):
        raise DocumentStorageError("Document names must be safe plain filenames.")
    if Path(filename).suffix.casefold() not in SUPPORTED_DOCUMENT_SUFFIXES:
        raise DocumentStorageError(f"Unsupported document format: {filename}")
    return filename
