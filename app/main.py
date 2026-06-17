import os
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from app.database import init_db
from app.routers import dashboard, projects, pipeline, prompts, analytics, settings, tasks

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Auto-initialize database tables and seed defaults on startup
    await init_db()
    yield

app = FastAPI(
    title="ACMP Solo Web App",
    description="Self-hosted YouTube Faceless Content Pipeline Manager",
    lifespan=lifespan
)

# Ensure static directories exist
static_dir = os.path.join(os.path.dirname(__file__), "static")
os.makedirs(os.path.join(static_dir, "css"), exist_ok=True)
os.makedirs(os.path.join(static_dir, "js"), exist_ok=True)

# Mount static files
app.mount("/static", StaticFiles(directory=static_dir), name="static")

# Mount projects assets directory to serve generated media
from app.config import PROJECTS_DIR
os.makedirs(PROJECTS_DIR, exist_ok=True)
app.mount("/projects", StaticFiles(directory=PROJECTS_DIR), name="projects")

# Include routers
app.include_router(dashboard.router)
app.include_router(projects.router)
app.include_router(pipeline.router)
app.include_router(prompts.router)
app.include_router(analytics.router)
app.include_router(settings.router)
app.include_router(tasks.router)
