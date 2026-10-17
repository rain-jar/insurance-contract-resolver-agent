from __future__ import annotations

import hmac
import json
import logging
import os
import secrets
import time
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import asynccontextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Callable
from urllib.parse import urlsplit
from uuid import uuid4

import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from openai import OpenAI
from pydantic import BaseModel, ConfigDict, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.middleware.sessions import SessionMiddleware

from .application import (
    AnalysisDocument,
    AnalysisInputError,
    AnalysisLimits,
    ContractAnalysis,
    ContractAnalysisService,
)
from .generation import OpenAIStructuredGenerator, StructuredGenerator
from .ingestion import DocumentIngestor
from .logging_utils import configure_json_logging
from .persistence import SQLiteRepository
from .relationship_retrieval import RelationshipDrivenResolver
from .retrieval import Embedder, HybridRetriever, OpenAIEmbedder
from .storage import DocumentStorageError, LocalDocumentStore, UploadSource


@dataclass(frozen=True)
class APISettings:
    data_directory: Path
    database_path: Path
    embedding_model: str = "text-embedding-3-small"
    limits: AnalysisLimits = AnalysisLimits()
    retention_days: int | None = None
    invite_codes: tuple[tuple[str, str], ...] = ()
    session_secret: str | None = None
    allowed_hosts: tuple[str, ...] = ("127.0.0.1", "localhost", "testserver")
    secure_cookies: bool = False
    max_stacks_per_reviewer: int = 10
    max_daily_analyses_per_reviewer: int = 20
    max_daily_analyses_global: int = 100

    @property
    def authentication_enabled(self) -> bool:
        return bool(self.invite_codes)

    @classmethod
    def from_environment(cls) -> "APISettings":
        data_directory = Path(
            os.environ.get("CONTRACT_STACK_DATA_DIR", ".local/contract-stack")
        )
        database_path = Path(
            os.environ.get(
                "CONTRACT_STACK_DATABASE", data_directory / "contract-stack.sqlite3"
            )
        )
        invite_codes = _parse_invite_codes(
            os.environ.get("CONTRACT_STACK_INVITE_CODES")
        )
        session_secret = os.environ.get("CONTRACT_STACK_SESSION_SECRET")
        if invite_codes and not session_secret:
            raise ValueError(
                "CONTRACT_STACK_SESSION_SECRET is required when invite access is enabled"
            )
        allowed_hosts = tuple(
            item.strip()
            for item in os.environ.get(
                "CONTRACT_STACK_ALLOWED_HOSTS", "127.0.0.1,localhost,testserver"
            ).split(",")
            if item.strip()
        )
        return cls(
            data_directory=data_directory,
            database_path=database_path,
            embedding_model=os.environ.get(
                "OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"
            ),
            retention_days=_optional_positive_int(
                os.environ.get("CONTRACT_STACK_RETENTION_DAYS"),
                "CONTRACT_STACK_RETENTION_DAYS",
            ),
            invite_codes=invite_codes,
            session_secret=session_secret,
            allowed_hosts=allowed_hosts,
            secure_cookies=_environment_bool("CONTRACT_STACK_SECURE_COOKIES", False),
            max_stacks_per_reviewer=_environment_positive_int(
                "CONTRACT_STACK_MAX_STACKS_PER_REVIEWER", 10
            ),
            max_daily_analyses_per_reviewer=_environment_positive_int(
                "CONTRACT_STACK_MAX_DAILY_ANALYSES_PER_REVIEWER", 20
            ),
            max_daily_analyses_global=_environment_positive_int(
                "CONTRACT_STACK_MAX_DAILY_ANALYSES_GLOBAL", 100
            ),
        )


class AnalysisCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=2_000)


EmbeddingFactory = Callable[[Path], Embedder | None]

CSRF_COOKIE = "contract_stack_csrf"
UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
LOGGER = logging.getLogger("contract_stack")


class AnalysisProcessor:
    def __init__(
        self,
        *,
        repository: SQLiteRepository,
        storage: LocalDocumentStore,
        settings: APISettings,
        generator: StructuredGenerator,
        embedding_factory: EmbeddingFactory,
    ) -> None:
        self.repository = repository
        self.storage = storage
        self.settings = settings
        self.generator = generator
        self.embedding_factory = embedding_factory

    def process(self, analysis_id: str, stack_id: str, question: str) -> None:
        started = time.monotonic()
        stack = self.repository.get_stack(stack_id)
        if stack is None:
            error = KeyError("Contract stack not found.")
            self.repository.fail_analysis(
                analysis_id, error, public_message="Contract stack not found."
            )
            raise error
        self.repository.mark_analysis_running(analysis_id)
        try:
            documents = [
                AnalysisDocument(
                    source_path=self.storage.document_path(
                        stack_id, item["relative_path"]
                    ),
                    display_name=item["display_name"],
                )
                for item in stack["documents"]
            ]
            embedder = self.embedding_factory(
                self.storage.embedding_cache_path(stack_id)
            )
            service = ContractAnalysisService(
                ingestor=DocumentIngestor(
                    cache_dir=self.storage.ingestion_cache_path(stack_id)
                ),
                retriever=HybridRetriever(embedder),
                resolver=RelationshipDrivenResolver(self.generator),
                limits=self.settings.limits,
            )
            analysis = service.analyze(question, documents)
            self.repository.complete_analysis(
                analysis_id,
                _serialize_analysis(
                    analysis,
                    settings=self.settings,
                    generator=self.generator,
                    embedder=embedder,
                ),
            )
            LOGGER.info(
                "analysis_completed",
                extra={
                    "analysis_id": analysis_id,
                    "stack_id": stack_id,
                    "elapsed_seconds": round(time.monotonic() - started, 6),
                },
            )
        except AnalysisInputError as exc:
            self.repository.fail_analysis(analysis_id, exc)
            _log_analysis_failure(analysis_id, stack_id, exc, started)
            raise
        except Exception as exc:
            self.repository.fail_analysis(
                analysis_id,
                exc,
                public_message="Analysis failed.",
            )
            _log_analysis_failure(analysis_id, stack_id, exc, started)
            raise


class BackgroundAnalysisJobs:
    def __init__(self, processor: AnalysisProcessor) -> None:
        self.processor = processor
        self.executor = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="contract-analysis",
        )

    def submit(self, analysis_id: str, stack_id: str, question: str) -> None:
        future = self.executor.submit(
            self.processor.process, analysis_id, stack_id, question
        )
        future.add_done_callback(_consume_job_exception)

    def shutdown(self) -> None:
        self.executor.shutdown(wait=True, cancel_futures=False)


def _consume_job_exception(future: Future) -> None:
    # The processor persists the failure; consuming it avoids an unobserved future.
    future.exception()


def create_app(
    settings: APISettings,
    *,
    generator: StructuredGenerator | None = None,
    embedding_factory: EmbeddingFactory | None = None,
) -> FastAPI:
    settings.data_directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    settings.data_directory.chmod(0o700)
    repository = SQLiteRepository(settings.database_path)
    storage = LocalDocumentStore(settings.data_directory / "stacks", settings.limits)

    if generator is None:
        client = OpenAI(max_retries=5, timeout=180.0)
        generator = OpenAIStructuredGenerator(client)
        if embedding_factory is None:
            embedding_factory = lambda cache: OpenAIEmbedder(
                client, settings.embedding_model, cache_dir=cache
            )
    elif embedding_factory is None:
        # Injected test generators default to deterministic lexical retrieval.
        embedding_factory = lambda _: None

    processor = AnalysisProcessor(
        repository=repository,
        storage=storage,
        settings=settings,
        generator=generator,
        embedding_factory=embedding_factory,
    )
    jobs = BackgroundAnalysisJobs(processor)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        repository.fail_interrupted_analyses()
        _purge_expired_stacks(repository, storage, settings.retention_days)
        yield
        jobs.shutdown()

    app = FastAPI(
        title="Contract Stack Resolver",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=list(settings.allowed_hosts),
    )
    app.state.repository = repository
    app.state.storage = storage
    app.state.jobs = jobs
    app.state.settings = settings
    package_root = Path(__file__).parent
    templates = Jinja2Templates(directory=package_root / "templates")
    app.mount("/static", StaticFiles(directory=package_root / "static"), name="static")

    @app.middleware("http")
    async def add_request_audit(request: Request, call_next):
        request_id = str(uuid4())
        started = time.monotonic()
        try:
            response = await call_next(request)
        except Exception:
            LOGGER.exception(
                "request_failed",
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "elapsed_seconds": round(time.monotonic() - started, 6),
                },
            )
            raise
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=()"
        )
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; base-uri 'self'; form-action 'self'; "
            "frame-ancestors 'none'; object-src 'none'; "
            "script-src 'self'; style-src 'self'"
        )
        if settings.authentication_enabled and not request.url.path.startswith(
            "/static/"
        ):
            response.headers["Cache-Control"] = "no-store"
        if settings.secure_cookies:
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )
        LOGGER.info(
            "request_completed",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "elapsed_seconds": round(time.monotonic() - started, 6),
            },
        )
        return response

    @app.middleware("http")
    async def reject_cross_site_mutations(request: Request, call_next):
        if request.method in UNSAFE_METHODS:
            origin = request.headers.get("origin")
            referer = request.headers.get("referer")
            fetch_site = request.headers.get("sec-fetch-site")
            if fetch_site == "cross-site" or (
                (origin or referer) is not None
                and not _is_allowed_origin(
                    origin or referer or "", settings.allowed_hosts
                )
            ):
                return JSONResponse(
                    status_code=403,
                    content={"detail": "Cross-site mutation rejected."},
                )
        return await call_next(request)

    @app.middleware("http")
    async def require_invite_authentication(request: Request, call_next):
        if not settings.authentication_enabled:
            request.state.reviewer_id = "local"
            return await call_next(request)
        public_path = request.url.path in {"/health", "/login"} or request.url.path.startswith(
            "/static/"
        )
        reviewer_id = request.session.get("reviewer_id")
        valid_reviewer_ids = {item[0] for item in settings.invite_codes}
        if reviewer_id is not None and reviewer_id not in valid_reviewer_ids:
            request.session.clear()
            reviewer_id = None
        if public_path:
            request.state.reviewer_id = reviewer_id
            return await call_next(request)
        if reviewer_id is None:
            if request.url.path.startswith("/api/"):
                return JSONResponse(status_code=401, content={"detail": "Authentication required."})
            return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
        request.state.reviewer_id = reviewer_id
        return await call_next(request)

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", **repository.health()}

    @app.get("/login", response_class=HTMLResponse, include_in_schema=False)
    def login_page(request: Request) -> HTMLResponse:
        if not settings.authentication_enabled or request.session.get("reviewer_id"):
            return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
        return _render(
            templates,
            request,
            "login.html",
            page_title="Reviewer access",
            authentication_page=True,
        )

    @app.post("/login", response_class=HTMLResponse, include_in_schema=False)
    def login(request: Request, access_code: str = Form(...)) -> HTMLResponse:
        reviewer_id = _match_invite(access_code, settings.invite_codes)
        if reviewer_id is None:
            return _render(
                templates,
                request,
                "login.html",
                page_title="Reviewer access",
                authentication_page=True,
                login_error="That access code is invalid or has expired.",
                status_code=401,
            )
        request.session.clear()
        request.session["reviewer_id"] = reviewer_id
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)

    @app.post("/logout", include_in_schema=False)
    def logout(
        request: Request, csrf_token: str = Form(...)
    ) -> RedirectResponse:
        _verify_csrf(request, csrf_token)
        request.session.clear()
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    @app.post("/api/stacks", status_code=status.HTTP_201_CREATED)
    def create_stack(
        request: Request,
        title: str = Form(default="Untitled contract stack", max_length=200),
        files: list[UploadFile] = File(...),
    ) -> dict:
        try:
            owner_id = _reviewer_id(request)
            _enforce_stack_quota(repository, settings, owner_id)
            record = _store_uploaded_stack(
                repository, storage, title, files, owner_id=owner_id
            )
        except DocumentStorageError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return _public_stack(record)

    @app.get("/api/stacks")
    def list_stacks(request: Request) -> list[dict]:
        return repository.list_stacks(owner_id=_reviewer_id(request))

    @app.get("/api/stacks/{stack_id}")
    def get_stack(request: Request, stack_id: str) -> dict:
        record = repository.get_stack(stack_id, owner_id=_reviewer_id(request))
        if record is None:
            raise HTTPException(status_code=404, detail="Contract stack not found.")
        return _public_stack(record)

    @app.delete("/api/stacks/{stack_id}", status_code=status.HTTP_204_NO_CONTENT)
    def delete_stack(request: Request, stack_id: str) -> None:
        if repository.get_stack(stack_id, owner_id=_reviewer_id(request)) is None:
            raise HTTPException(status_code=404, detail="Contract stack not found.")
        try:
            storage.delete_stack(stack_id)
        except DocumentStorageError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        repository.delete_stack(stack_id)

    @app.post(
        "/api/stacks/{stack_id}/analyses",
        status_code=status.HTTP_201_CREATED,
    )
    def create_analysis(
        stack_id: str, payload: AnalysisCreateRequest, request: Request
    ) -> dict:
        owner_id = _reviewer_id(request)
        stack = repository.get_stack(stack_id, owner_id=owner_id)
        if stack is None:
            raise HTTPException(status_code=404, detail="Contract stack not found.")

        analysis_id = str(uuid4())
        _enforce_analysis_quota(repository, settings, owner_id)
        question = payload.question.strip()
        repository.create_analysis(analysis_id, stack_id, question)
        try:
            processor.process(analysis_id, stack_id, question)
        except AnalysisInputError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail={
                    "message": "Analysis failed.",
                    "analysis_id": analysis_id,
                },
            ) from exc
        record = repository.get_analysis(analysis_id)
        if record is None:
            raise RuntimeError("The completed analysis could not be reloaded.")
        return record

    @app.get("/api/stacks/{stack_id}/analyses")
    def list_analyses(request: Request, stack_id: str) -> list[dict]:
        if repository.get_stack(stack_id, owner_id=_reviewer_id(request)) is None:
            raise HTTPException(status_code=404, detail="Contract stack not found.")
        return repository.list_analyses(stack_id)

    @app.get("/api/analyses/{analysis_id}")
    def get_analysis(request: Request, analysis_id: str) -> dict:
        record = repository.get_analysis(analysis_id, owner_id=_reviewer_id(request))
        if record is None:
            raise HTTPException(status_code=404, detail="Analysis not found.")
        return record

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    def dashboard(request: Request) -> HTMLResponse:
        stacks = repository.list_stacks(owner_id=_reviewer_id(request))
        return _render(
            templates,
            request,
            "dashboard.html",
            page_title="Contract stacks",
            stacks=stacks,
            stack_count=len(stacks),
            document_count=sum(item["document_count"] for item in stacks),
        )

    @app.get("/stacks/new", response_class=HTMLResponse, include_in_schema=False)
    def new_stack(request: Request) -> HTMLResponse:
        return _render(
            templates,
            request,
            "new_stack.html",
            page_title="New contract stack",
        )

    @app.post("/stacks", include_in_schema=False)
    def create_stack_page(
        request: Request,
        csrf_token: str = Form(...),
        title: str = Form(default="Untitled contract stack", max_length=200),
        files: list[UploadFile] = File(...),
    ) -> RedirectResponse:
        _verify_csrf(request, csrf_token)
        try:
            owner_id = _reviewer_id(request)
            _enforce_stack_quota(repository, settings, owner_id)
            record = _store_uploaded_stack(
                repository, storage, title, files, owner_id=owner_id
            )
        except DocumentStorageError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return RedirectResponse(
            url=f"/stacks/{record['id']}", status_code=status.HTTP_303_SEE_OTHER
        )

    @app.get(
        "/stacks/{stack_id}",
        response_class=HTMLResponse,
        include_in_schema=False,
    )
    def stack_page(request: Request, stack_id: str) -> HTMLResponse:
        stack = repository.get_stack(stack_id, owner_id=_reviewer_id(request))
        if stack is None:
            raise HTTPException(status_code=404, detail="Contract stack not found.")
        return _render(
            templates,
            request,
            "stack.html",
            page_title=stack["title"],
            stack=_public_stack(stack),
            analyses=repository.list_analyses(stack_id),
        )

    @app.post("/stacks/{stack_id}/analyses", include_in_schema=False)
    def create_analysis_page(
        request: Request,
        stack_id: str,
        csrf_token: str = Form(...),
        question: str = Form(..., min_length=1, max_length=2_000),
    ) -> RedirectResponse:
        _verify_csrf(request, csrf_token)
        owner_id = _reviewer_id(request)
        if repository.get_stack(stack_id, owner_id=owner_id) is None:
            raise HTTPException(status_code=404, detail="Contract stack not found.")
        _enforce_analysis_quota(repository, settings, owner_id)
        clean_question = question.strip()
        if not clean_question:
            raise HTTPException(status_code=422, detail="A question is required.")
        analysis_id = str(uuid4())
        repository.create_analysis(analysis_id, stack_id, clean_question)
        jobs.submit(analysis_id, stack_id, clean_question)
        return RedirectResponse(
            url=f"/analyses/{analysis_id}", status_code=status.HTTP_303_SEE_OTHER
        )

    @app.get(
        "/analyses/{analysis_id}",
        response_class=HTMLResponse,
        include_in_schema=False,
    )
    def analysis_page(request: Request, analysis_id: str) -> HTMLResponse:
        owner_id = _reviewer_id(request)
        record = repository.get_analysis(analysis_id, owner_id=owner_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Analysis not found.")
        stack = repository.get_stack(record["stack_id"], owner_id=owner_id)
        if stack is None:
            raise HTTPException(status_code=404, detail="Contract stack not found.")
        return _render(
            templates,
            request,
            "analysis.html",
            page_title="Analysis result",
            analysis=_analysis_view(record),
            stack=_public_stack(stack),
        )

    @app.get(
        "/analyses/{analysis_id}/status",
        response_class=JSONResponse,
        include_in_schema=False,
    )
    def analysis_status(request: Request, analysis_id: str) -> dict:
        record = repository.get_analysis(analysis_id, owner_id=_reviewer_id(request))
        if record is None:
            raise HTTPException(status_code=404, detail="Analysis not found.")
        return {
            "id": record["id"],
            "status": record["status"],
            "completed_at_utc": record["completed_at_utc"],
        }

    @app.post("/stacks/{stack_id}/delete", include_in_schema=False)
    def delete_stack_page(
        request: Request,
        stack_id: str,
        csrf_token: str = Form(...),
    ) -> RedirectResponse:
        _verify_csrf(request, csrf_token)
        if repository.get_stack(stack_id, owner_id=_reviewer_id(request)) is None:
            raise HTTPException(status_code=404, detail="Contract stack not found.")
        storage.delete_stack(stack_id)
        repository.delete_stack(stack_id)
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)

    @app.post("/analyses/{analysis_id}/retry", include_in_schema=False)
    def retry_analysis_page(
        request: Request,
        analysis_id: str,
        csrf_token: str = Form(...),
    ) -> RedirectResponse:
        _verify_csrf(request, csrf_token)
        owner_id = _reviewer_id(request)
        original = repository.get_analysis(analysis_id, owner_id=owner_id)
        if original is None:
            raise HTTPException(status_code=404, detail="Analysis not found.")
        if original["status"] != "FAILED":
            raise HTTPException(status_code=409, detail="Only failed analyses can be retried.")
        if repository.get_stack(original["stack_id"], owner_id=owner_id) is None:
            raise HTTPException(status_code=404, detail="Contract stack not found.")
        _enforce_analysis_quota(repository, settings, owner_id)
        retry_id = str(uuid4())
        repository.create_analysis(
            retry_id,
            original["stack_id"],
            original["question"],
        )
        jobs.submit(retry_id, original["stack_id"], original["question"])
        return RedirectResponse(
            url=f"/analyses/{retry_id}", status_code=status.HTTP_303_SEE_OTHER
        )

    # Added last so signed session state is available to every function middleware.
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.session_secret or secrets.token_urlsafe(48),
        session_cookie="contract_stack_session",
        same_site="lax",
        https_only=settings.secure_cookies,
        max_age=8 * 60 * 60,
    )
    return app


def _store_uploaded_stack(
    repository: SQLiteRepository,
    storage: LocalDocumentStore,
    title: str,
    files: list[UploadFile],
    *,
    owner_id: str = "local",
) -> dict:
    clean_title = title.strip() or "Untitled contract stack"
    stack_id = str(uuid4())
    uploads = [
        UploadSource(filename=item.filename or "", stream=item.file) for item in files
    ]
    stored = storage.save_stack(stack_id, uploads)
    try:
        return repository.create_stack(
            stack_id, clean_title, stored, owner_id=owner_id
        )
    except Exception:
        storage.delete_stack(stack_id)
        raise


def _public_stack(record: dict) -> dict:
    return {
        "id": record["id"],
        "title": record["title"],
        "created_at_utc": record["created_at_utc"],
        "documents": [
            {
                "display_name": item["display_name"],
                "byte_size": item["byte_size"],
                "sha256": item["sha256"],
            }
            for item in record["documents"]
        ],
    }


def _render(
    templates: Jinja2Templates,
    request: Request,
    template_name: str,
    **context,
) -> HTMLResponse:
    response_status = context.pop("status_code", 200)
    token = request.cookies.get(CSRF_COOKIE) or secrets.token_urlsafe(32)
    response = templates.TemplateResponse(
        request=request,
        name=template_name,
        context={
            **context,
            "csrf_token": token,
            "authentication_enabled": request.app.state.settings.authentication_enabled,
            "reviewer_id": getattr(request.state, "reviewer_id", None),
        },
        status_code=response_status,
    )
    if request.cookies.get(CSRF_COOKIE) is None:
        response.set_cookie(
            CSRF_COOKIE,
            token,
            httponly=True,
            samesite="strict",
            secure=request.app.state.settings.secure_cookies,
        )
    return response


def _verify_csrf(request: Request, submitted: str) -> None:
    expected = request.cookies.get(CSRF_COOKIE)
    if expected is None or not hmac.compare_digest(expected, submitted):
        raise HTTPException(status_code=403, detail="Invalid form security token.")


def _is_allowed_origin(origin: str, allowed_hosts: tuple[str, ...]) -> bool:
    parsed = urlsplit(origin)
    if parsed.scheme not in {"http", "https"} or parsed.hostname is None:
        return False
    return any(
        parsed.hostname == allowed
        or (allowed.startswith("*.") and parsed.hostname.endswith(allowed[1:]))
        for allowed in allowed_hosts
    )


def _reviewer_id(request: Request) -> str:
    reviewer_id = getattr(request.state, "reviewer_id", None)
    if not reviewer_id:
        raise HTTPException(status_code=401, detail="Authentication required.")
    return str(reviewer_id)


def _match_invite(
    submitted: str, invite_codes: tuple[tuple[str, str], ...]
) -> str | None:
    candidate = submitted.strip()
    for reviewer_id, access_code in invite_codes:
        if hmac.compare_digest(candidate, access_code):
            return reviewer_id
    return None


def _enforce_stack_quota(
    repository: SQLiteRepository, settings: APISettings, owner_id: str
) -> None:
    if not settings.authentication_enabled:
        return
    if repository.count_stacks(owner_id) >= settings.max_stacks_per_reviewer:
        raise HTTPException(
            status_code=429,
            detail="Reviewer contract-stack quota reached. Delete a stack before adding another.",
        )


def _enforce_analysis_quota(
    repository: SQLiteRepository, settings: APISettings, owner_id: str
) -> None:
    if not settings.authentication_enabled:
        return
    since = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    if (
        repository.count_analyses_since(since, owner_id=owner_id)
        >= settings.max_daily_analyses_per_reviewer
    ):
        raise HTTPException(
            status_code=429,
            detail="Reviewer daily analysis quota reached.",
        )
    if (
        repository.count_analyses_since(since)
        >= settings.max_daily_analyses_global
    ):
        raise HTTPException(
            status_code=429,
            detail="Demo daily analysis capacity reached.",
        )


def _analysis_view(record: dict) -> dict:
    payload = record.get("result") or {}
    resolution = payload.get("result")
    chain = []
    if resolution is not None:
        chain = [
            {**step, "display_value": _format_value(step.get("value"))}
            for step in resolution.get("amendment_chain", [])
        ]
    technical = {
        "configuration": payload.get("configuration"),
        "audit": payload.get("audit"),
        "relationships": payload.get("relationships"),
        "relationship_expansion": payload.get("relationship_expansion"),
        "provenance_errors": {
            "extraction": payload.get("extraction_provenance_errors"),
            "expansion": payload.get("expansion_provenance_errors"),
            "result": payload.get("result_provenance_errors"),
        },
    }
    return {
        **record,
        "resolution": resolution,
        "display_value": (
            _format_value(resolution.get("normalized_value"))
            if resolution is not None
            else None
        ),
        "chain": chain,
        "technical_json": json.dumps(technical, indent=2),
    }


def _format_value(value: dict | None) -> str | None:
    if value is None:
        return None
    if value.get("amount") is not None:
        amount = f"{value['amount']:,}"
        currency = value.get("currency") or ""
        return f"{currency} {amount}".strip()
    start = value.get("start")
    end = value.get("end")
    if start or end:
        return f"{_friendly_datetime(start)} → {_friendly_datetime(end)}"
    return "No active value"


def _friendly_datetime(value: str | None) -> str:
    return value.replace("T", " ") if value else "—"


def _log_analysis_failure(
    analysis_id: str,
    stack_id: str,
    error: Exception,
    started: float,
) -> None:
    LOGGER.error(
        "analysis_failed",
        extra={
            "analysis_id": analysis_id,
            "stack_id": stack_id,
            "error_type": type(error).__name__,
            "elapsed_seconds": round(time.monotonic() - started, 6),
        },
    )


def _purge_expired_stacks(
    repository: SQLiteRepository,
    storage: LocalDocumentStore,
    retention_days: int | None,
) -> int:
    if retention_days is None:
        return 0
    cutoff = datetime.now(UTC) - timedelta(days=retention_days)
    expired_ids = repository.list_expired_stack_ids(cutoff.isoformat())
    deleted = 0
    for stack_id in expired_ids:
        try:
            storage.delete_stack(stack_id)
        except Exception as exc:
            LOGGER.error(
                "retention_delete_failed",
                extra={"stack_id": stack_id, "error_type": type(exc).__name__},
            )
            continue
        repository.delete_stack(stack_id)
        deleted += 1
    if deleted:
        LOGGER.info("retention_cleanup_completed", extra={"deleted_count": deleted})
    return deleted


def _optional_positive_int(value: str | None, name: str) -> int | None:
    if value is None or not value.strip():
        return None
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be a positive integer") from exc
    if parsed <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return parsed


def _environment_positive_int(name: str, default: int) -> int:
    return _optional_positive_int(os.environ.get(name, str(default)), name) or default


def _environment_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    normalized = value.strip().casefold()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be true or false")


def _parse_invite_codes(value: str | None) -> tuple[tuple[str, str], ...]:
    if value is None or not value.strip():
        return ()
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError("CONTRACT_STACK_INVITE_CODES must be a JSON object") from exc
    if not isinstance(parsed, dict) or not parsed:
        raise ValueError("CONTRACT_STACK_INVITE_CODES must be a non-empty JSON object")
    result: list[tuple[str, str]] = []
    seen_codes: set[str] = set()
    for reviewer_id, access_code in parsed.items():
        if (
            not isinstance(reviewer_id, str)
            or not reviewer_id.strip()
            or not isinstance(access_code, str)
            or len(access_code) < 20
        ):
            raise ValueError(
                "Each invite must map a reviewer name to an access code of at least 20 characters"
            )
        if access_code in seen_codes:
            raise ValueError("Reviewer access codes must be unique")
        seen_codes.add(access_code)
        result.append((reviewer_id.strip(), access_code))
    return tuple(result)


def _serialize_analysis(
    analysis: ContractAnalysis,
    *,
    settings: APISettings,
    generator: StructuredGenerator,
    embedder: Embedder | None,
) -> dict:
    run = analysis.run
    generation_metadata = (
        run.initial_run.api_metadata or run.expansion_api_metadata or {}
    )
    return {
        "result": run.result.model_dump(mode="json"),
        "initial_result": run.initial_run.result.model_dump(mode="json"),
        "initial_extracted_events": [
            event.model_dump(mode="json")
            for event in run.initial_run.extracted_events
        ],
        "expansion_events": [
            event.model_dump(mode="json") for event in run.expansion_events
        ],
        "combined_events": [
            event.model_dump(mode="json") for event in run.combined_events
        ],
        "ordered_events": [
            event.model_dump(mode="json") for event in run.ordered_events
        ],
        "relationships": [
            relationship.model_dump(mode="json")
            for relationship in run.relationships
        ],
        "relationship_expansion": {
            "triggered": run.expansion.triggered,
            "reasons": run.expansion.reasons,
            "query": run.expansion.query,
            "added": [
                {
                    "chunk_id": item.chunk.chunk_id,
                    "document_path": item.chunk.document_path,
                    "locator": item.chunk.locator,
                    "extraction_method": item.chunk.extraction_method.value,
                    "score": item.score,
                    "rank": item.rank,
                }
                for item in run.expansion.added
            ],
        },
        "initial_api_metadata": run.initial_run.api_metadata,
        "expansion_api_metadata": run.expansion_api_metadata,
        "extraction_provenance_errors": (
            run.initial_run.extraction_provenance_errors
        ),
        "expansion_provenance_errors": run.expansion_provenance_errors,
        "result_provenance_errors": analysis.result_provenance_errors,
        "documents": [asdict(item) for item in analysis.documents],
        "audit": asdict(analysis.audit),
        "configuration": {
            "generation": {
                "adapter": type(generator).__name__,
                "requested_model": generation_metadata.get("requested_model"),
                "reasoning_effort": generation_metadata.get("reasoning_effort"),
                "reasoning_mode": generation_metadata.get("reasoning_mode"),
                "requested_service_tier": generation_metadata.get(
                    "requested_service_tier"
                ),
                "max_output_tokens": generation_metadata.get("max_output_tokens"),
            },
            "retrieval": {
                "top_k": settings.limits.top_k,
                "mode": "HYBRID" if embedder is not None else "LEXICAL_ONLY",
                "embedding_model": (
                    settings.embedding_model if embedder is not None else None
                ),
            },
            "relationship_expansion": {
                "maximum_rounds": 1,
                "maximum_added_chunks": 2,
                "maximum_additional_extraction_calls": 1,
            },
        },
    }


def run() -> None:
    configure_json_logging(os.environ.get("LOG_LEVEL", "INFO"))
    host = os.environ.get("CONTRACT_STACK_HOST", "127.0.0.1")
    port = _optional_positive_int(os.environ.get("PORT", "8000"), "PORT")
    uvicorn.run(
        create_app(APISettings.from_environment()),
        host=host,
        port=port or 8000,
        access_log=False,
    )
