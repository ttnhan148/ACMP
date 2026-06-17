from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
import aiosqlite
from app.database import get_db
from app.templates import templates
from app.services import project_service, voice_service

router = APIRouter(prefix="/projects", tags=["projects"])

@router.get("", response_class=HTMLResponse)
async def list_projects(request: Request, db: aiosqlite.Connection = Depends(get_db)):
    projects = await project_service.get_projects(db)
    return templates.TemplateResponse(
        "projects.html",
        {"request": request, "projects": projects, "page": "projects"}
    )

@router.get("/new", response_class=HTMLResponse)
async def new_project_form(request: Request, db: aiosqlite.Connection = Depends(get_db)):
    # Load default settings to pre-populate form
    cursor = await db.execute("SELECT key, value FROM settings")
    settings = {row[0]: row[1] for row in await cursor.fetchall()}
    
    return templates.TemplateResponse(
        "project_new.html",
        {
            "request": request, 
            "defaults": settings, 
            "voices": voice_service.VOICES,
            "page": "projects"
        }
    )

@router.post("", response_class=HTMLResponse)
async def create_new_project(
    request: Request,
    title: str = Form(...),
    topic: str = Form(...),
    niche: str = Form(""),
    language: str = Form("en"),
    voice_preset: str = Form("guy"),
    duration_target: int = Form(480),
    notes: str = Form(""),
    db: aiosqlite.Connection = Depends(get_db)
):
    project = await project_service.create_project(
        db, title, topic, niche, language, voice_preset, duration_target, notes
    )
    
    # Redirect to the newly created project's pipeline page
    return RedirectResponse(url=f"/projects/{project['id']}", status_code=303)

@router.get("/{project_id}", response_class=HTMLResponse)
async def get_project_detail(project_id: int, request: Request, db: aiosqlite.Connection = Depends(get_db)):
    project = await project_service.get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
        
    return templates.TemplateResponse(
        "project_detail.html",
        {
            "request": request, 
            "project": project, 
            "voices": voice_service.VOICES,
            "page": "projects"
        }
    )

@router.delete("/{project_id}")
async def delete_project(project_id: int, request: Request, db: aiosqlite.Connection = Depends(get_db)):
    success = await project_service.delete_project(db, project_id)
    if not success:
        raise HTTPException(status_code=400, detail="Failed to delete project")
        
    # If client requested via HTMX, return a blank response or a redirect headers
    if request.headers.get("HX-Request"):
        # We can send HX-Redirect to make HTMX trigger a full reload to /projects
        return HTMLResponse(
            status_code=200, 
            headers={"HX-Redirect": "/projects"}
        )
    return RedirectResponse(url="/projects", status_code=303)
