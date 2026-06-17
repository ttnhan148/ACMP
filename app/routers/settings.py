from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse
import aiosqlite
from app.database import get_db
from app.templates import templates
from app.services import voice_service

router = APIRouter(prefix="/settings", tags=["settings"])

@router.get("", response_class=HTMLResponse)
async def get_settings(request: Request, db: aiosqlite.Connection = Depends(get_db)):
    cursor = await db.execute("SELECT key, value FROM settings")
    settings_data = {row[0]: row[1] for row in await cursor.fetchall()}
    
    return templates.TemplateResponse(
        "settings.html",
        {
            "request": request, 
            "settings": settings_data, 
            "voices": voice_service.VOICES,
            "page": "settings"
        }
    )

@router.post("", response_class=RedirectResponse)
async def update_settings(
    request: Request,
    channel_name: str = Form(""),
    default_niche: str = Form("history"),
    default_language: str = Form("en"),
    default_voice: str = Form("guy"),
    default_duration: str = Form("480"),
    projects_dir: str = Form("./projects"),
    ffmpeg_path: str = Form("ffmpeg"),
    auto_backup: str = Form("false"),
    db: aiosqlite.Connection = Depends(get_db)
):
    updates = {
        "channel_name": channel_name,
        "default_niche": default_niche,
        "default_language": default_language,
        "default_voice": default_voice,
        "default_duration": default_duration,
        "projects_dir": projects_dir,
        "ffmpeg_path": ffmpeg_path,
        "auto_backup": auto_backup
    }
    
    for key, value in updates.items():
        await db.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            (key, value)
        )
    await db.commit()
    
    return RedirectResponse(url="/settings", status_code=303)
