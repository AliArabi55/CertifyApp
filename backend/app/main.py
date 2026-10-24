"""FastAPI entrypoint: mounts the API routers and serves the static frontend."""
import base64
import binascii
import hmac
import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from app.routes_email import router as email_router
from app.routes_gmail import router as gmail_router
from app.routes_projects import router as projects_router

APP_DIR = Path(__file__).resolve().parent
BASE_DIR = APP_DIR.parent.parent if APP_DIR.parent.name == "backend" else APP_DIR.parent
FRONTEND_DIR = BASE_DIR / "frontend"

APP_USERNAME = os.environ.get("CERTIFY_USERNAME", "admin")
APP_PASSWORD = os.environ.get("CERTIFY_PASSWORD")  # Unset = open access (local use only).

app = FastAPI(title="Certify - Certificate & Mail Merge Tool")
app.add_middleware(GZipMiddleware, minimum_size=1024)


def _credentials_valid(header: str) -> bool:
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "basic":
        return False
    try:
        user, _, password = base64.b64decode(token).decode("utf-8").partition(":")
    except (binascii.Error, UnicodeDecodeError):
        return False
    return hmac.compare_digest(user.encode(), APP_USERNAME.encode()) & hmac.compare_digest(
        password.encode(), APP_PASSWORD.encode()
    )


@app.middleware("http")
async def require_login(request: Request, call_next):
    if APP_PASSWORD and request.url.path != "/health" and not _credentials_valid(request.headers.get("authorization", "")):
        return Response(status_code=401, headers={"WWW-Authenticate": 'Basic realm="Certify"'})
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


app.include_router(projects_router)
app.include_router(email_router)
app.include_router(gmail_router)

app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


@app.get("/")
def index():
    return FileResponse(FRONTEND_DIR / "index.html")
