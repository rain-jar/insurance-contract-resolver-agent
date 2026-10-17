from io import BytesIO
from pathlib import Path
from uuid import uuid4

import pytest

from contract_stack.application import AnalysisLimits
from contract_stack.storage import (
    DocumentStorageError,
    LocalDocumentStore,
    UploadSource,
)


def test_stack_storage_is_scoped_and_deletion_removes_derived_data(
    tmp_path: Path,
) -> None:
    store = LocalDocumentStore(tmp_path / "stacks")
    stack_id = str(uuid4())

    documents = store.save_stack(
        stack_id,
        [UploadSource(filename="policy.txt", stream=BytesIO(b"Policy text"))],
    )
    store.ingestion_cache_path(stack_id).joinpath("cache.json").write_text("{}")
    store.embedding_cache_path(stack_id).joinpath("vector.json").write_text("[]")

    assert documents[0].relative_path == "documents/policy.txt"
    assert store.document_path(stack_id, documents[0].relative_path).read_bytes() == b"Policy text"
    assert store.stack_path(stack_id).exists()

    store.delete_stack(stack_id)

    assert not store.stack_path(stack_id).exists()


def test_failed_upload_is_removed_atomically(tmp_path: Path) -> None:
    stack_id = str(uuid4())
    store = LocalDocumentStore(
        tmp_path / "stacks",
        AnalysisLimits(max_document_bytes=4),
    )

    with pytest.raises(DocumentStorageError, match="exceeds"):
        store.save_stack(
            stack_id,
            [UploadSource(filename="policy.txt", stream=BytesIO(b"too large"))],
        )

    assert not store.stack_path(stack_id).exists()
    assert not (store.incoming_root / stack_id).exists()


def test_stack_storage_rejects_unsafe_filename(tmp_path: Path) -> None:
    store = LocalDocumentStore(tmp_path / "stacks")

    with pytest.raises(DocumentStorageError, match="safe plain filenames"):
        store.save_stack(
            str(uuid4()),
            [UploadSource(filename="../policy.txt", stream=BytesIO(b"text"))],
        )
