"""FastAPI entrypoint: mounts the API routers and serves the static frontend."""
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.routes_email import router as email_router
from app.routes_gmail import router as gmail_router
from app.routes_projects import router as projects_router

BASE_DIR = Path(__file__).resolve().parent.parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"

app = FastAPI(title="Certify - Certificate & Mail Merge Tool")


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
