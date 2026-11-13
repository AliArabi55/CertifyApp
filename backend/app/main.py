"""FastAPI entrypoint: mounts the API routers and serves the static frontend."""
import os
import re
import time
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from app import auth_store
from app.routes_auth import router as auth_router
from app.routes_email import router as email_router
from app.routes_gmail import router as gmail_router
from app.routes_projects import router as projects_router

APP_DIR = Path(__file__).resolve().parent
BASE_DIR = APP_DIR.parent.parent if APP_DIR.parent.name == "backend" else APP_DIR.parent
FRONTEND_DIR = BASE_DIR / "frontend"

app = FastAPI(title="Certify - Certificate & Mail Merge Tool")
app.add_middleware(GZipMiddleware, minimum_size=1024)
auth_store.init_db()

PUBLIC_AUTH_PATHS = {
    "/api/auth/register",
    "/api/auth/verify",
    "/api/auth/login",
    "/api/auth/me",
    "/api/auth/password-reset-request",
    "/api/auth/password-reset",
}
PROJECT_PATH = re.compile(r"^/api/projects/([a-f0-9]{10})(?:/|$)")


@app.middleware("http")
async def authenticate_and_isolate_projects(request: Request, call_next):
    path = request.url.path
    if path == "/api/auth/me":
        session_token = request.cookies.get("certify_session")
        user = auth_store.get_session_user(session_token, int(time.time())) if session_token else None
        if not user:
            return JSONResponse(status_code=401, content={"detail": "Sign in to continue."})
        request.state.user = user
        return await call_next(request)

    if path in {"/", "/health"} or path.startswith("/static/") or path in PUBLIC_AUTH_PATHS:
        return await call_next(request)

    session_token = request.cookies.get("certify_session")
    user = auth_store.get_session_user(session_token, int(time.time())) if session_token else None
    if not user:
        return JSONResponse(status_code=401, content={"detail": "Sign in to continue."})
    request.state.user = user

    if request.method not in {"GET", "HEAD", "OPTIONS"} and not auth_store.csrf_valid(
        user, request.headers.get("x-csrf-token", "")
    ):
        return JSONResponse(status_code=403, content={"detail": "Request verification failed."})

    match = PROJECT_PATH.match(path)
    if match and not auth_store.owns_project(user["id"], match.group(1)):
        return JSONResponse(status_code=404, content={"detail": "Project or file not found"})
    return await call_next(request)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.exception_handler(FileNotFoundError)
async def missing_file_handler(request, exc):
    return JSONResponse(status_code=404, content={"detail": "Project or file not found"})


@app.exception_handler(ValueError)
async def invalid_input_handler(request, exc):
    return JSONResponse(status_code=400, content={"detail": str(exc)})


app.include_router(auth_router)
app.include_router(projects_router)
app.include_router(email_router)
app.include_router(gmail_router)

app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


@app.get("/")
def index():
    return FileResponse(FRONTEND_DIR / "index.html")
