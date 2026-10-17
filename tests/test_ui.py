import time
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
from contract_stack.web import APISettings, CSRF_COOKIE, create_app


class _FakeGenerator:
    def generate(self, **_: object) -> StructuredGeneration:
        return StructuredGeneration(
            output=ProvisionExtraction(events=_events()),
            metadata={
                "requested_model": "fake-ui-test-model",
                "reasoning_effort": "none",
                "reasoning_mode": "test",
                "requested_service_tier": "test",
                "max_output_tokens": 100,
                "usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
            },
        )


class _FailOnceGenerator(_FakeGenerator):
    def __init__(self) -> None:
        self.calls = 0

    def generate(self, **kwargs: object) -> StructuredGeneration:
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("controlled first-attempt failure")
        return super().generate(**kwargs)


def test_reviewer_ui_upload_analyze_review_and_delete(tmp_path: Path) -> None:
    app = create_app(
        APISettings(
            data_directory=tmp_path / "data",
            database_path=tmp_path / "data" / "app.sqlite3",
        ),
        generator=_FakeGenerator(),
    )
    with TestClient(app) as client:
        dashboard = client.get("/")
        assert dashboard.status_code == 200
        assert "Find the term that governs now" in dashboard.text
        csrf = client.cookies[CSRF_COOKIE]

        created = client.post(
            "/stacks",
            data={"title": "Example policy", "csrf_token": csrf},
            files={
                "files": (
                    "contract.txt",
                    "Base declarations set the On Premises limit to USD 3,500,000. "
                    "Endorsement 8 replaces the On Premises limit with USD 5,000,000.",
                    "text/plain",
                )
            },
            follow_redirects=False,
        )
        assert created.status_code == 303
        stack_path = created.headers["location"]
        stack_id = stack_path.rsplit("/", 1)[-1]

        stack_page = client.get(stack_path)
        assert "Example policy" in stack_page.text
        assert "contract.txt" in stack_page.text

        submitted = client.post(
            f"/stacks/{stack_id}/analyses",
            data={
                "csrf_token": csrf,
                "question": "What is the current On Premises limit?",
            },
            follow_redirects=False,
        )
        assert submitted.status_code == 303
        analysis_path = submitted.headers["location"]
        analysis_id = analysis_path.rsplit("/", 1)[-1]

        status = None
        for _ in range(100):
            status = client.get(f"/analyses/{analysis_id}/status").json()["status"]
            if status in {"COMPLETED", "FAILED"}:
                break
            time.sleep(0.01)
        assert status == "COMPLETED"

        result = client.get(analysis_path)
        assert result.status_code == 200
        assert "USD 5,000,000" in result.text
        assert "Endorsement 8" in result.text
        assert "Supporting evidence" in result.text
        assert "Technical audit details" in result.text

        deleted = client.post(
            f"/stacks/{stack_id}/delete",
            data={"csrf_token": csrf},
            follow_redirects=False,
        )
        assert deleted.status_code == 303
        assert client.get(stack_path).status_code == 404


def test_reviewer_forms_require_csrf_token(tmp_path: Path) -> None:
    app = create_app(
        APISettings(tmp_path / "data", tmp_path / "data" / "app.sqlite3"),
        generator=_FakeGenerator(),
    )
    with TestClient(app) as client:
        client.get("/")
        response = client.post(
            "/stacks",
            data={"title": "Example", "csrf_token": "wrong"},
            files={"files": ("contract.txt", "Policy text", "text/plain")},
        )

    assert response.status_code == 403


def test_cross_site_api_mutation_is_rejected(tmp_path: Path) -> None:
    app = create_app(
        APISettings(tmp_path / "data", tmp_path / "data" / "app.sqlite3"),
        generator=_FakeGenerator(),
    )
    with TestClient(app) as client:
        response = client.post(
            "/api/stacks",
            headers={"Origin": "https://malicious.example"},
            files={"files": ("contract.txt", "Policy text", "text/plain")},
        )

    assert response.status_code == 403
    assert response.json()["detail"] == "Cross-site mutation rejected."


def test_cross_site_referer_is_rejected_when_origin_is_absent(tmp_path: Path) -> None:
    app = create_app(
        APISettings(tmp_path / "data", tmp_path / "data" / "app.sqlite3"),
        generator=_FakeGenerator(),
    )
    with TestClient(app) as client:
        response = client.post(
            "/api/stacks",
            headers={"Referer": "https://malicious.example/form"},
            files={"files": ("contract.txt", "Policy text", "text/plain")},
        )

    assert response.status_code == 403
    assert response.json()["detail"] == "Cross-site mutation rejected."


def test_failed_analysis_can_be_retried_from_reviewer_page(tmp_path: Path) -> None:
    generator = _FailOnceGenerator()
    app = create_app(
        APISettings(tmp_path / "data", tmp_path / "data" / "app.sqlite3"),
        generator=generator,
    )
    with TestClient(app) as client:
        dashboard = client.get("/")
        csrf = client.cookies[CSRF_COOKIE]
        created = client.post(
            "/stacks",
            data={"title": "Retry policy", "csrf_token": csrf},
            files={
                "files": (
                    "contract.txt",
                    "Base declarations set the On Premises limit to USD 3,500,000. "
                    "Endorsement 8 replaces the On Premises limit with USD 5,000,000.",
                    "text/plain",
                )
            },
            follow_redirects=False,
        )
        stack_id = created.headers["location"].rsplit("/", 1)[-1]
        submitted = client.post(
            f"/stacks/{stack_id}/analyses",
            data={
                "csrf_token": csrf,
                "question": "What is the current On Premises limit?",
            },
            follow_redirects=False,
        )
        failed_path = submitted.headers["location"]
        failed_id = failed_path.rsplit("/", 1)[-1]
        for _ in range(100):
            if client.get(f"/analyses/{failed_id}/status").json()["status"] == "FAILED":
                break
            time.sleep(0.01)

        failed_page = client.get(failed_path)
        assert "Retry analysis" in failed_page.text
        retried = client.post(
            f"/analyses/{failed_id}/retry",
            data={"csrf_token": csrf},
            follow_redirects=False,
        )
        assert retried.status_code == 303
        retry_path = retried.headers["location"]
        retry_id = retry_path.rsplit("/", 1)[-1]
        assert retry_id != failed_id
        for _ in range(100):
            status = client.get(f"/analyses/{retry_id}/status").json()["status"]
            if status in {"COMPLETED", "FAILED"}:
                break
            time.sleep(0.01)
        assert status == "COMPLETED"


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
