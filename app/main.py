import uuid
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from app.config import settings
from app.core.logging import setup_logging
from app.core.exceptions import register_exception_handlers
from app.db.base import engine
from app.db.redis import init_redis, close_redis
from app.api.v1.router import router as api_v1_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    await init_redis()
    yield
    await close_redis()
    await engine.dispose()


app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    debug=settings.debug,
    lifespan=lifespan,
    docs_url="/docs" if settings.debug else None,
    redoc_url=None,
)

register_exception_handlers(app)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    request.state.request_id = str(uuid.uuid4())
    response = await call_next(request)
    response.headers["X-Request-ID"] = request.state.request_id
    return response


@app.get("/health", tags=["system"])
async def health():
    return {"status": "ok"}


app.include_router(api_v1_router)
