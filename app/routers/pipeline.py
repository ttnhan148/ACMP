from fastapi import APIRouter, Request, Depends, Form, File, UploadFile, HTTPException, BackgroundTasks
from fastapi.responses import HTMLResponse
import aiosqlite
import os
import json
import aiofiles
from datetime import datetime
from typing import List, Optional
from app.database import get_db
from app.templates import templates
from app.services import project_service, voice_service, video_service, youtube_service, analytics_service

router = APIRouter(prefix="/projects/{project_id}/steps", tags=["pipeline"])

@router.get("/timeline", response_class=HTMLResponse)
async def get_timeline(project_id: int, request: Request, db: aiosqlite.Connection = Depends(get_db)):
    """Renders the vertical step list checklist timeline component."""
    project = await project_service.get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return templates.TemplateResponse(
        "components/pipeline_timeline.html",
        {"request": request, "project": project}
    )

@router.get("/{step_key}/panel", response_class=HTMLResponse)
async def get_step_panel(project_id: int, step_key: str, request: Request, db: aiosqlite.Connection = Depends(get_db)):
    """Renders the HTML partial for a specific pipeline step detail panel."""
    project = await project_service.get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
        
    # Find active step
    step = next((s for s in project["pipeline_steps"] if s["step_key"] == step_key), None)
    if not step:
        raise HTTPException(status_code=404, detail="Step not found")
        
    # Get associated prompt for this step if applicable
    prompt_mapping = {
        "research": "P-01: Topic Research",
        "script": "P-02: Script Writing",
        "images": "P-03: Scene Descriptions + Image Prompts",
        "thumbnail": "P-04: Thumbnail Concept",
        "seo": "P-05: SEO Metadata",
        "compliance": "P-07: Compliance Review"
    }
    
    prompt = None
    if step_key in prompt_mapping:
        cursor = await db.execute("SELECT * FROM prompts WHERE name = ?", (prompt_mapping[step_key],))
        row = await cursor.fetchone()
        if row:
            prompt = dict(row)
            # Parse variables from string back to list
            prompt["variables"] = json.loads(prompt["variables"])
            
    # Read current step data if already saved in artifacts
    step_data = {}
    if step_key == "research":
        research_art = next((a for a in project["artifacts"] if a["type"] == "notes"), None)
        if research_art and os.path.exists(research_art["file_path"]):
            async with aiofiles.open(research_art["file_path"], mode='r', encoding='utf-8') as f:
                step_data["notes"] = await f.read()
    elif step_key == "script":
        script_art = next((a for a in project["artifacts"] if a["type"] == "script"), None)
        if script_art and os.path.exists(script_art["file_path"]):
            async with aiofiles.open(script_art["file_path"], mode='r', encoding='utf-8') as f:
                step_data["script"] = await f.read()
    elif step_key == "seo":
        seo_art = next((a for a in project["artifacts"] if a["type"] == "metadata"), None)
        if seo_art and os.path.exists(seo_art["file_path"]):
            async with aiofiles.open(seo_art["file_path"], mode='r', encoding='utf-8') as f:
                try:
                    step_data["seo"] = json.loads(await f.read())
                except Exception:
                    step_data["seo"] = {}
                    
    # Render corresponding panel template
    template_name = f"pipeline/panel_{step_key}.html"
    return templates.TemplateResponse(
        template_name,
        {
            "request": request,
            "project": project,
            "step": step,
            "prompt": prompt,
            "data": step_data,
            "voices": voice_service.VOICES
        }
    )

@router.post("/{step_key}/status", response_class=HTMLResponse)
async def update_step_status(
    project_id: int,
    step_key: str,
    request: Request,
    status: str = Form(...),
    notes: str = Form(""),
    db: aiosqlite.Connection = Depends(get_db)
):
    """Updates step status (HTMX endpoint) and returns updated timeline component."""
    project = await project_service.update_step(db, project_id, step_key, status, notes)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
        
    return templates.TemplateResponse(
        "components/pipeline_timeline.html",
        {"request": request, "project": project}
    )

# --- INDIVIDUAL STEP API SUB-HANDLERS ---

@router.post("/research/save", response_class=HTMLResponse)
async def save_research(
    project_id: int,
    request: Request,
    notes: str = Form(...),
    db: aiosqlite.Connection = Depends(get_db)
):
    project = await project_service.get_project(db, project_id)
    file_path = os.path.join(project_service.PROJECTS_DIR, str(project_id), "research_notes.txt")
    
    async with aiofiles.open(file_path, mode='w', encoding='utf-8') as f:
        await f.write(notes)
        
    file_size = os.path.getsize(file_path)
    await project_service.add_artifact(db, project_id, "notes", file_path, file_size)
    
    # Mark step done
    project = await project_service.update_step(db, project_id, "research", "done", "Research notes saved.")
    
    return templates.TemplateResponse(
        "components/pipeline_timeline.html",
        {"request": request, "project": project, "hx_trigger": "step-updated"}
    )

@router.post("/script/save", response_class=HTMLResponse)
async def save_script(
    project_id: int,
    request: Request,
    script_text: str = Form(...),
    db: aiosqlite.Connection = Depends(get_db)
):
    file_path = os.path.join(project_service.PROJECTS_DIR, str(project_id), "script.txt")
    
    async with aiofiles.open(file_path, mode='w', encoding='utf-8') as f:
        await f.write(script_text)
        
    file_size = os.path.getsize(file_path)
    await project_service.add_artifact(db, project_id, "script", file_path, file_size)
    
    # Mark step done
    project = await project_service.update_step(db, project_id, "script", "done", f"Script saved ({len(script_text.split())} words).")
    
    return templates.TemplateResponse(
        "components/pipeline_timeline.html",
        {"request": request, "project": project}
    )

# Async Background task execution for Edge-TTS
async def run_voice_gen_task(project_id: int, text: str, voice_preset: str, rate: str, db_path: str):
    # Establish separate connection for background thread
    async with aiosqlite.connect(db_path) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        
        # Create Task record
        cursor = await db.execute(
            "INSERT INTO tasks (project_id, task_type, status, progress_pct, started_at) VALUES (?, 'voice_gen', 'running', 20, CURRENT_TIMESTAMP)",
            (project_id,)
        )
        task_id = cursor.lastrowid
        await db.commit()
        
        try:
            output_file = os.path.join(project_service.PROJECTS_DIR, str(project_id), "voice.mp3")
            
            # Simulate intermediate progress
            await db.execute("UPDATE tasks SET progress_pct = 50 WHERE id = ?", (task_id,))
            await db.commit()
            
            # Generate speech file
            await voice_service.generate_voice_file(text, voice_preset, output_file, rate)
            
            # Add artifact record
            file_size = os.path.getsize(output_file)
            # Add artifact inside this thread
            cursor_art = await db.execute(
                "SELECT MAX(version) FROM artifacts WHERE project_id = ? AND type = 'voice'",
                (project_id,)
            )
            v_row = await cursor_art.fetchone()
            version = (v_row[0] or 0) + 1 if v_row else 1
            await db.execute(
                "INSERT INTO artifacts (project_id, type, file_path, file_size, version) VALUES (?, 'voice', ?, ?, ?)",
                (project_id, output_file, file_size, version)
            )
            
            # Update task success
            await db.execute("UPDATE tasks SET status = 'done', progress_pct = 100, completed_at = CURRENT_TIMESTAMP WHERE id = ?", (task_id,))
            
            # Update step status to done
            completed_at = datetime.utcnow().isoformat()
            await db.execute(
                "UPDATE pipeline_steps SET status = 'done', completed_at = ?, notes = 'Voice narration audio synthesized successfully.' WHERE project_id = ? AND step_key = 'voice'",
                (completed_at, project_id)
            )
            await db.commit()
            
        except Exception as e:
            # Update task error
            await db.execute(
                "UPDATE tasks SET status = 'failed', error_log = ?, completed_at = CURRENT_TIMESTAMP WHERE id = ?",
                (str(e), task_id)
            )
            # Roll back pipeline step to pending/failed
            await db.execute(
                "UPDATE pipeline_steps SET status = 'pending', notes = ? WHERE project_id = ? AND step_key = 'voice'",
                (f"Voice generation failed: {str(e)}", project_id)
            )
            await db.commit()

@router.post("/voice/generate", response_class=HTMLResponse)
async def generate_voice(
    project_id: int,
    request: Request,
    background_tasks: BackgroundTasks,
    rate: str = Form("+0%"),
    db: aiosqlite.Connection = Depends(get_db)
):
    project = await project_service.get_project(db, project_id)
    # Read script file
    script_art = next((a for a in project["artifacts"] if a["type"] == "script"), None)
    if not script_art or not os.path.exists(script_art["file_path"]):
        raise HTTPException(status_code=400, detail="Cannot generate voice: write and save script first.")
        
    async with aiofiles.open(script_art["file_path"], mode='r', encoding='utf-8') as f:
        script_text = await f.read()
        
    # Queue background thread
    from app.config import DB_PATH
    background_tasks.add_task(
        run_voice_gen_task, 
        project_id, 
        script_text, 
        project["voice_preset"], 
        rate, 
        str(DB_PATH.absolute())
    )
    
    # Temporarily mark step in_progress
    project = await project_service.update_step(db, project_id, "voice", "in_progress", "Voice synthesis queued in background worker...")
    
    return templates.TemplateResponse(
        "components/pipeline_timeline.html",
        {"request": request, "project": project}
    )

@router.post("/images/upload", response_class=HTMLResponse)
async def upload_scenes(
    project_id: int,
    request: Request,
    files: List[UploadFile] = File(...),
    db: aiosqlite.Connection = Depends(get_db)
):
    scenes_dir = os.path.join(project_service.PROJECTS_DIR, str(project_id), "scenes")
    os.makedirs(scenes_dir, exist_ok=True)
    
    uploaded_count = 0
    for file in files:
        if not file.filename:
            continue
        file_path = os.path.join(scenes_dir, file.filename)
        async with aiofiles.open(file_path, mode='wb') as out_file:
            content = await file.read()
            await out_file.write(content)
            
        file_size = os.path.getsize(file_path)
        await project_service.add_artifact(db, project_id, "scene_image", file_path, file_size)
        uploaded_count += 1
        
    # Mark step done if files uploaded
    if uploaded_count > 0:
        project = await project_service.update_step(db, project_id, "images", "done", f"Uploaded {uploaded_count} scene images.")
    else:
        project = await project_service.get_project(db, project_id)
        
    return templates.TemplateResponse(
        "components/pipeline_timeline.html",
        {"request": request, "project": project}
    )

# Async Background task execution for FFmpeg Video Assembly
async def run_video_assembly_task(project_id: int, resolution: str, fps: int, db_path: str):
    async with aiosqlite.connect(db_path) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        
        cursor = await db.execute(
            "INSERT INTO tasks (project_id, task_type, status, progress_pct, started_at) VALUES (?, 'assembly', 'running', 10, CURRENT_TIMESTAMP)",
            (project_id,)
        )
        task_id = cursor.lastrowid
        await db.commit()
        
        try:
            project_dir = os.path.join(project_service.PROJECTS_DIR, str(project_id))
            
            async def progress_cb(pct):
                async with aiosqlite.connect(db_path) as sub_db:
                    await sub_db.execute("UPDATE tasks SET progress_pct = ? WHERE id = ?", (pct, task_id))
                    await sub_db.commit()
            
            # Assemble video
            output_file = await video_service.assemble_video(
                project_dir=project_dir,
                resolution=resolution,
                fps=fps,
                progress_callback=progress_cb
            )
            
            # Add artifact record
            file_size = os.path.getsize(output_file)
            cursor_art = await db.execute(
                "SELECT MAX(version) FROM artifacts WHERE project_id = ? AND type = 'video'",
                (project_id,)
            )
            v_row = await cursor_art.fetchone()
            version = (v_row[0] or 0) + 1 if v_row else 1
            await db.execute(
                "INSERT INTO artifacts (project_id, type, file_path, file_size, version) VALUES (?, 'video', ?, ?, ?)",
                (project_id, output_file, file_size, version)
            )
            
            # Update task success
            await db.execute("UPDATE tasks SET status = 'done', progress_pct = 100, completed_at = CURRENT_TIMESTAMP WHERE id = ?", (task_id,))
            
            # Update step status
            completed_at = datetime.utcnow().isoformat()
            await db.execute(
                "UPDATE pipeline_steps SET status = 'done', completed_at = ?, notes = 'Video rendering completed successfully.' WHERE project_id = ? AND step_key = 'assembly'",
                (completed_at, project_id)
            )
            await db.commit()
            
        except Exception as e:
            await db.execute(
                "UPDATE tasks SET status = 'failed', error_log = ?, completed_at = CURRENT_TIMESTAMP WHERE id = ?",
                (str(e), task_id)
            )
            await db.execute(
                "UPDATE pipeline_steps SET status = 'pending', notes = ? WHERE project_id = ? AND step_key = 'assembly'",
                (f"Video assembly failed: {str(e)}", project_id)
            )
            await db.commit()

@router.post("/assembly/assemble", response_class=HTMLResponse)
async def assemble_video(
    project_id: int,
    request: Request,
    background_tasks: BackgroundTasks,
    resolution: str = Form("1920x1080"),
    fps: int = Form(30),
    db: aiosqlite.Connection = Depends(get_db)
):
    project = await project_service.get_project(db, project_id)
    # Check if voice.mp3 and scene images are ready
    voice_art = next((a for a in project["artifacts"] if a["type"] == "voice"), None)
    if not voice_art or not os.path.exists(voice_art["file_path"]):
        raise HTTPException(status_code=400, detail="Voice narration audio missing. Run Generate Voice step first.")
        
    scene_images = [a for a in project["artifacts"] if a["type"] == "scene_image"]
    if not scene_images:
        raise HTTPException(status_code=400, detail="Scene images missing. Upload scene images first.")
        
    from app.config import DB_PATH
    background_tasks.add_task(
        run_video_assembly_task, 
        project_id, 
        resolution, 
        fps, 
        str(DB_PATH.absolute())
    )
    
    project = await project_service.update_step(db, project_id, "assembly", "in_progress", "FFmpeg video composition started in background worker...")
    
    return templates.TemplateResponse(
        "components/pipeline_timeline.html",
        {"request": request, "project": project}
    )

@router.post("/thumbnail/upload", response_class=HTMLResponse)
async def upload_thumbnail(
    project_id: int,
    request: Request,
    file: UploadFile = File(...),
    db: aiosqlite.Connection = Depends(get_db)
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file uploaded")
        
    dest_path = os.path.join(project_service.PROJECTS_DIR, str(project_id), "thumbnail.png")
    async with aiofiles.open(dest_path, mode='wb') as out_file:
        content = await file.read()
        await out_file.write(content)
        
    file_size = os.path.getsize(dest_path)
    await project_service.add_artifact(db, project_id, "thumbnail", dest_path, file_size)
    
    # Mark step done
    project = await project_service.update_step(db, project_id, "thumbnail", "done", "Thumbnail image uploaded.")
    
    return templates.TemplateResponse(
        "components/pipeline_timeline.html",
        {"request": request, "project": project}
    )

@router.post("/seo/save", response_class=HTMLResponse)
async def save_seo(
    project_id: int,
    request: Request,
    title: str = Form(...),
    description: str = Form(...),
    tags: str = Form(...),
    db: aiosqlite.Connection = Depends(get_db)
):
    seo_data = {
        "title": title,
        "description": description,
        "tags": [t.strip() for t in tags.split(",") if t.strip()]
    }
    
    dest_path = os.path.join(project_service.PROJECTS_DIR, str(project_id), "metadata.json")
    async with aiofiles.open(dest_path, mode='w', encoding='utf-8') as f:
        await f.write(json.dumps(seo_data, indent=2))
        
    file_size = os.path.getsize(dest_path)
    await project_service.add_artifact(db, project_id, "metadata", dest_path, file_size)
    
    # Mark step done
    project = await project_service.update_step(db, project_id, "seo", "done", "SEO metadata generated and saved.")
    
    return templates.TemplateResponse(
        "components/pipeline_timeline.html",
        {"request": request, "project": project}
    )

@router.post("/compliance/check", response_class=HTMLResponse)
async def check_compliance(
    project_id: int,
    request: Request,
    copyright_chk: str = Form("pending"),
    policy_chk: str = Form("pending"),
    safety_chk: str = Form("pending"),
    originality_chk: str = Form("pending"),
    db: aiosqlite.Connection = Depends(get_db)
):
    chk_notes = f"Compliance Checklist results:\n- Copyright: {copyright_chk}\n- Policy: {policy_chk}\n- Brand Safety: {safety_chk}\n- Originality: {originality_chk}"
    
    # Mark step done if all pass
    status = "done" if "pending" not in [copyright_chk, policy_chk, safety_chk, originality_chk] else "in_progress"
    
    project = await project_service.update_step(db, project_id, "compliance", status, chk_notes)
    
    return templates.TemplateResponse(
        "components/pipeline_timeline.html",
        {"request": request, "project": project}
    )

@router.post("/publish/run", response_class=HTMLResponse)
async def run_publish(
    project_id: int,
    request: Request,
    privacy: str = Form("unlisted"),
    db: aiosqlite.Connection = Depends(get_db)
):
    project = await project_service.get_project(db, project_id)
    # Check if video is assembled
    video_art = next((a for a in project["artifacts"] if a["type"] == "video"), None)
    if not video_art or not os.path.exists(video_art["file_path"]):
        raise HTTPException(status_code=400, detail="Cannot publish: Assemble final video first.")
        
    # Read SEO metadata
    seo_art = next((a for a in project["artifacts"] if a["type"] == "metadata"), None)
    seo_title = project["title"]
    seo_desc = "Auto-uploaded by ACMP Solo."
    seo_tags = []
    if seo_art and os.path.exists(seo_art["file_path"]):
        async with aiofiles.open(seo_art["file_path"], mode='r', encoding='utf-8') as f:
            try:
                meta = json.loads(await f.read())
                seo_title = meta.get("title", seo_title)
                seo_desc = meta.get("description", seo_desc)
                seo_tags = meta.get("tags", seo_tags)
            except Exception:
                pass
                
    # Run uploading
    upload_res = await youtube_service.publish_video(
        video_path=video_art["file_path"],
        title=seo_title,
        description=seo_desc,
        tags=seo_tags,
        privacy_status=privacy
    )
    
    # Update project DB details
    await project_service.update_project(db, project_id, {
        "youtube_url": upload_res["youtube_url"],
        "youtube_video_id": upload_res["video_id"],
        "status": "published"
    })
    
    # Mark step done
    project = await project_service.update_step(db, project_id, "publish", "done", f"Published to YouTube (Video ID: {upload_res['video_id']}).")
    
    # Auto-seed initial analytics stats immediately so the dashboard analytics is instantly populated
    await analytics_service.sync_project_analytics(db, project_id)
    
    return templates.TemplateResponse(
        "components/pipeline_timeline.html",
        {"request": request, "project": project, "hx_trigger": "step-updated"}
    )

@router.post("/tracking/sync", response_class=HTMLResponse)
async def sync_tracking(
    project_id: int,
    request: Request,
    db: aiosqlite.Connection = Depends(get_db)
):
    # Sync metrics
    await analytics_service.sync_project_analytics(db, project_id)
    
    # Mark step done
    project = await project_service.update_step(db, project_id, "tracking", "done", "Analytics metrics successfully synced from YouTube.")
    
    return templates.TemplateResponse(
        "components/pipeline_timeline.html",
        {"request": request, "project": project}
    )
