import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from contract_stack.generation import StructuredGeneration
from contract_stack.models import (
    Attribute,
    EvidenceRef,
    ExtractionMethod,
    NormalizedValue,
    Operation,
    OrderingInfo,
    ProvisionEvent,
    ProvisionExtraction,
    SourceRef,
)
from contract_stack.web import APISettings, create_app


class _FakeGenerator:
    def __init__(self, extraction: ProvisionExtraction) -> None:
        self.extraction = extraction
        self.calls = 0

    def generate(self, **_: object) -> StructuredGeneration:
        self.calls += 1
        return StructuredGeneration(
            output=self.extraction,
            metadata={
                "requested_model": "fake-api-test-model",
                "reasoning_effort": "none",
                "usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
            },
        )


class _FailingGenerator:
    def generate(self, **_: object) -> StructuredGeneration:
        raise RuntimeError("controlled generation failure")


def test_stack_analysis_and_delete_api_workflow(tmp_path: Path) -> None:
    generator = _FakeGenerator(ProvisionExtraction(events=_events()))
    settings = _settings(tmp_path)
    client = TestClient(create_app(settings, generator=generator))

    health = client.get("/health")
    assert health.json() == {"status": "ok", "database": "ok", "schema_version": 1}
    assert health.headers["X-Request-ID"]

    created = client.post(
        "/api/stacks",
        data={"title": "Example policy"},
        files={
            "files": (
                "contract.txt",
                "Base declarations set the On Premises limit to USD 3,500,000. "
                "Endorsement 8 replaces the On Premises limit with USD 5,000,000.",
                "text/plain",
            )
        },
    )
    assert created.status_code == 201
    stack = created.json()
    stack_id = stack["id"]
    assert stack["title"] == "Example policy"
    assert stack["documents"][0]["display_name"] == "contract.txt"
    assert "relative_path" not in stack["documents"][0]
    assert client.get("/api/stacks").json() == [
        {
            "id": stack_id,
            "title": "Example policy",
            "created_at_utc": stack["created_at_utc"],
            "document_count": 1,
        }
    ]

    completed = client.post(
        f"/api/stacks/{stack_id}/analyses",
        json={"question": "What is the current On Premises limit?"},
    )
    assert completed.status_code == 201
    record = completed.json()
    analysis_id = record["id"]
    assert record["status"] == "COMPLETED"
    assert record["result"]["result"]["normalized_value"]["amount"] == 5_000_000
    assert record["result"]["audit"]["generation_call_count"] == 1
    assert record["result"]["result_provenance_errors"] == []
    assert record["result"]["configuration"]["retrieval"] == {
        "top_k": 8,
        "mode": "LEXICAL_ONLY",
        "embedding_model": None,
    }
    assert str(tmp_path) not in completed.text
    assert generator.calls == 1
    summaries = client.get(f"/api/stacks/{stack_id}/analyses")
    assert summaries.status_code == 200
    assert summaries.json()[0]["id"] == analysis_id
    assert summaries.json()[0]["status"] == "COMPLETED"
    assert "result" not in summaries.json()[0]

    fetched = client.get(f"/api/analyses/{analysis_id}")
    assert fetched.status_code == 200
    assert fetched.json() == record
    assert (settings.data_directory / "stacks" / stack_id / "derived").exists()

    deleted = client.delete(f"/api/stacks/{stack_id}")
    assert deleted.status_code == 204
    assert not (settings.data_directory / "stacks" / stack_id).exists()
    assert client.get(f"/api/stacks/{stack_id}").status_code == 404
    assert client.get(f"/api/analyses/{analysis_id}").status_code == 404


def test_api_state_survives_app_recreation(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    first = TestClient(
        create_app(
            settings,
            generator=_FakeGenerator(ProvisionExtraction(events=[])),
        )
    )
    created = first.post(
        "/api/stacks",
        files={"files": ("contract.txt", "Policy text", "text/plain")},
    )
    stack_id = created.json()["id"]

    second = TestClient(
        create_app(
            settings,
            generator=_FakeGenerator(ProvisionExtraction(events=[])),
        )
    )
    fetched = second.get(f"/api/stacks/{stack_id}")

    assert fetched.status_code == 200
    assert fetched.json()["documents"][0]["sha256"] == created.json()["documents"][0]["sha256"]


def test_api_rejects_unsafe_upload_name(tmp_path: Path) -> None:
    client = TestClient(
        create_app(
            _settings(tmp_path),
            generator=_FakeGenerator(ProvisionExtraction(events=[])),
        )
    )

    response = client.post(
        "/api/stacks",
        files={"files": ("../contract.txt", "Policy text", "text/plain")},
    )

    assert response.status_code == 422


def test_failed_analysis_is_persisted_with_retrievable_status(tmp_path: Path) -> None:
    client = TestClient(create_app(_settings(tmp_path), generator=_FailingGenerator()))
    created = client.post(
        "/api/stacks",
        files={"files": ("contract.txt", "The current limit is USD 5.", "text/plain")},
    )

    failed = client.post(
        f"/api/stacks/{created.json()['id']}/analyses",
        json={"question": "What is the current limit?"},
    )

    assert failed.status_code == 500
    analysis_id = failed.json()["detail"]["analysis_id"]
    persisted = client.get(f"/api/analyses/{analysis_id}")
    assert persisted.status_code == 200
    assert persisted.json()["status"] == "FAILED"
    assert persisted.json()["error_type"] == "RuntimeError"
    assert persisted.json()["error_message"] == "Analysis failed."
    assert persisted.json()["result"] is None


def test_configured_retention_removes_expired_stack_and_files(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    app = create_app(
        settings,
        generator=_FakeGenerator(ProvisionExtraction(events=[])),
    )
    with TestClient(app) as client:
        created = client.post(
            "/api/stacks",
            files={"files": ("contract.txt", "Policy text", "text/plain")},
        )
        stack_id = created.json()["id"]

    with sqlite3.connect(settings.database_path) as connection:
        connection.execute(
            "UPDATE stacks SET created_at_utc = '2000-01-01T00:00:00+00:00' "
            "WHERE id = ?",
            (stack_id,),
        )

    expiring_settings = APISettings(
        data_directory=settings.data_directory,
        database_path=settings.database_path,
        retention_days=30,
    )
    with TestClient(
        create_app(
            expiring_settings,
            generator=_FakeGenerator(ProvisionExtraction(events=[])),
        )
    ) as client:
        assert client.get(f"/api/stacks/{stack_id}").status_code == 404

    assert not (settings.data_directory / "stacks" / stack_id).exists()


def _settings(tmp_path: Path) -> APISettings:
    return APISettings(
        data_directory=tmp_path / "data",
        database_path=tmp_path / "data" / "app.sqlite3",
    )


def _events() -> list[ProvisionEvent]:
    return [
        _event(
            "Base declarations Item 2",
            Operation.BASE,
            3_500_000,
            "Base declarations set the On Premises limit to USD 3,500,000.",
        ),
        _event(
            "Endorsement 8",
            Operation.REPLACE,
            5_000_000,
            "Endorsement 8 replaces the On Premises limit with USD 5,000,000.",
            number=8,
        ),
    ]


def _event(
    label: str,
    operation: Operation,
    amount: int,
    quote: str,
    *,
    number: int | None = None,
) -> ProvisionEvent:
    return ProvisionEvent(
        attribute=Attribute.LIMIT,
        subject="On Premises",
        operation=operation,
        value=NormalizedValue(
            amount=amount,
            currency="USD",
            start=None,
            end=None,
        ),
        source=SourceRef(
            document_path="contract.txt",
            provision_label=label,
            locator="paragraph:1",
        ),
        evidence=[
            EvidenceRef(
                document_path="contract.txt",
                locator="paragraph:1",
                quote=quote,
                extraction_method=ExtractionMethod.TEXT,
            )
        ],
        ordering=OrderingInfo(
            order_number=number,
            effective_date=None,
            required_sources=[],
            supersedes=[],
        ),
    )
