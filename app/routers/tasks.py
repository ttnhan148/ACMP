from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse
import aiosqlite
from app.database import get_db
from app.templates import templates

router = APIRouter(prefix="/projects/{project_id}/tasks", tags=["tasks"])

@router.get("/active", response_class=HTMLResponse)
async def get_active_task_status(project_id: int, request: Request, db: aiosqlite.Connection = Depends(get_db)):
    """
    HTMX polling endpoint. Returns an active task's progress state.
    If a task is running, it returns a component that polls again.
    If no task is running, it triggers a step checklist refresh.
    """
    # 1. Fetch the most recent active or newly completed task
    cursor = await db.execute(
        """
        SELECT * FROM tasks 
        WHERE project_id = ? 
        ORDER BY started_at DESC LIMIT 1
        """,
        (project_id,)
    )
    row = await cursor.fetchone()
    if not row:
        return HTMLResponse(content="") # No tasks at all
        
    task = dict(row)
    
    # Map task types to human-readable names
    type_names = {
        "voice_gen": "Voice Synthesis (Edge-TTS)",
        "assembly": "Video Composition (FFmpeg)",
        "seo_gen": "SEO Metadata Synthesis",
        "thumbnail_gen": "Thumbnail Generation",
        "compliance_check": "Compliance Audit"
    }
    task["type_name"] = type_names.get(task["task_type"], task["task_type"])
    
    # 2. If running or queued, render progress bar with a polling trigger
    if task["status"] in ["queued", "running"]:
        return templates.TemplateResponse(
            "components/task_progress.html",
            {
                "request": request,
                "project_id": project_id,
                "task": task,
                "poll": True
            }
        )
        
    # 3. If finished recently (e.g. within last 10 seconds)
    # We display a brief success/fail banner and trigger HTMX to update the pipeline
    import datetime
    completed_at = None
    if task["completed_at"]:
        try:
            completed_at = datetime.datetime.fromisoformat(task["completed_at"].split(".")[0])
        except ValueError:
            pass
            
    is_recent = False
    if completed_at:
        # Check if completed within 10 seconds
        time_diff = datetime.datetime.utcnow() - completed_at
        if time_diff.total_seconds() < 10:
            is_recent = True
            
    if is_recent:
        # Return banner that does NOT poll, but triggers pipeline step reload
        return templates.TemplateResponse(
            "components/task_progress.html",
            {
                "request": request,
                "project_id": project_id,
                "task": task,
                "poll": False
            },
            headers={"HX-Trigger": "step-updated"}
        )
        
    # Default to empty response (completed long ago)
    return HTMLResponse(content="")
