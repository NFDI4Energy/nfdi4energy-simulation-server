"""FastAPI assembly. Task and monitor behavior lives in services and routers."""
import logging
from pathlib import Path
from fastapi import FastAPI, Request, Depends
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
import redis
from fastapi_app.authentication.auth import router as auth_router, get_current_user_or_none, create_oauth
from fastapi_app.persistence.database import create_database, init_db
from fastapi_app.persistence.database_dependencies import get_db
from fastapi_app.core.settings import Settings
from fastapi_app.frameworks.dacedsx.events.store import EventStore
from fastapi_app.frameworks.dacedsx.events.persistence import close_persistence
from fastapi_app.tasks.storage import TaskStorage, StorageError
from fastapi_app.tasks.status import StatusService
from fastapi_app.tasks.submission import SubmissionService, SubmissionError
from fastapi_app.frameworks.dacedsx.monitoring.service import MonitorService
from fastapi_app.tasks.dependencies import TaskNotFound
from fastapi_app.tasks.routes import router as task_router
from fastapi_app.frameworks.dacedsx.monitoring.routes import router as monitor_router
from fastapi_app.frameworks.dacedsx.routes import router as dacedsx_router
from fastapi_app.frameworks.dacedsx.submission import validate_scenario, LifecycleEvents
from fastapi_app.frameworks.dacedsx.status import EventEvidence
from fastapi_app.infrastructure.rabbitmq_client import SimulationQueue

logger = logging.getLogger(__name__)
SERVER_ROOT = Path(__file__).resolve().parent


def create_app(settings=None):
    settings = settings or Settings.from_env()
    app = FastAPI()
    app.add_middleware(SessionMiddleware, secret_key=settings.session_secret)
    app.include_router(auth_router)
    app.include_router(dacedsx_router)
    app.include_router(task_router)
    app.include_router(monitor_router)
    app.mount("/static", StaticFiles(directory=str(SERVER_ROOT / "static")), name="static")
    app.mount("/dashboard", StaticFiles(directory=str(SERVER_ROOT / "static/svelte-dist"), html=True), name="dashboard")
    templates = Jinja2Templates(directory=str(SERVER_ROOT / "templates"))

    @app.on_event("startup")
    def startup():
        settings.validate()
        app.state.settings = settings
        app.state.oauth = create_oauth(settings)
        engine, factory = create_database(settings.database_url)
        app.state.engine, app.state.session_factory = engine, factory
        try:
            init_db(engine)
            client = redis.Redis(host=settings.redis_host, port=6379, db=0,
                                 socket_connect_timeout=2, socket_timeout=2)
            app.state.redis = client
            app.state.storage = TaskStorage(settings.resources_dir, settings.results_dir)
            app.state.events = EventStore()
            app.state.status = StatusService(client, EventEvidence(app.state.storage, app.state.events))
            app.state.monitor = MonitorService(app.state.storage, app.state.events, app.state.status)
            app.state.submission = SubmissionService(
                settings, app.state.storage, client,
                lambda: SimulationQueue(host=settings.rabbitmq_host, queue_name="simulation_requests"),
                validate_scenario, LifecycleEvents(app.state.storage))
        except Exception:
            shutdown()
            raise

    @app.on_event("shutdown")
    def shutdown():
        for name, method in (("events", "close"), ("redis", "close"), ("engine", "dispose")):
            resource = getattr(app.state, name, None)
            if resource is not None:
                getattr(resource, method)()
        close_persistence()

    @app.exception_handler(TaskNotFound)
    async def task_not_found(request, exc):
        return JSONResponse({"error": "Task not found or access denied"}, status_code=404)

    @app.exception_handler(StorageError)
    async def invalid_path(request, exc):
        return JSONResponse({"error": str(exc), "code": "invalid_path"}, status_code=400)

    @app.exception_handler(SubmissionError)
    async def submission_error(request, exc):
        body = {"error": str(exc), "code": exc.code}
        if exc.task_id:
            body["task_id"] = exc.task_id
        return JSONResponse(body, status_code=exc.status_code)

    @app.exception_handler(OSError)
    async def storage_error(request, exc):
        logger.exception("Storage operation failed", exc_info=exc)
        return JSONResponse({"error": "Task storage is unavailable", "code": "storage_unavailable"}, status_code=503)

    @app.get("/")
    def index(request: Request, db=Depends(get_db)):
        return templates.TemplateResponse("index.html", {"request": request, "user": get_current_user_or_none(request, db)})

    return app


app = create_app()
