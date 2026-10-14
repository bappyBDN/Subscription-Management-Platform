import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routers import (auth, costs, dashboard, insights, masters, org, reports, requests, subscriptions, system,
                             teams)
from app.core.config import get_settings
from app.services import usage
from app.services.deletion import DeleteBlocked

logging.basicConfig(level=logging.INFO)
settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    stop = usage.start_auto_sync()
    yield
    if stop:
        stop.set()


app = FastAPI(
    title="SMP — Subscription Management Platform",
    description="BMD/AES paid-subscription register, request/approval workflow, credential handover and card cost tracking.",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.frontend_origin.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for r in (auth, org, teams, masters, subscriptions, requests, dashboard, costs, insights, reports, system):
    app.include_router(r.router, prefix="/api")


@app.exception_handler(DeleteBlocked)
async def delete_blocked(_: Request, exc: DeleteBlocked):
    return JSONResponse(status_code=409, content={"detail": str(exc)})


@app.get("/api/health", tags=["system"])
def health():
    return {"status": "ok"}


@app.middleware("http")
async def no_store_for_secrets(request, call_next):
    response = await call_next(request)
    if request.url.path.endswith("/reveal"):
        response.headers["Cache-Control"] = "no-store"
    return response
