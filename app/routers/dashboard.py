from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
import aiosqlite
from app.database import get_db
from app.templates import templates
from app.services import project_service, analytics_service, youtube_service

router = APIRouter()

@router.get("/", response_class=HTMLResponse)
@router.get("/dashboard", response_class=HTMLResponse)
async def get_dashboard(request: Request, db: aiosqlite.Connection = Depends(get_db)):
    # 1. Fetch channel-wide summary metrics
    summary = await analytics_service.get_channel_summary(db)
    
    # 2. Fetch recent projects
    projects = await project_service.get_projects(db)
    recent_projects = projects[:5] if projects else []
    
    # 3. Retrieve default niche from settings
    cursor = await db.execute("SELECT value FROM settings WHERE key = 'default_niche'")
    niche_row = await cursor.fetchone()
    niche = niche_row[0] if niche_row else "history"
    
    # 4. Fetch platform trending topics
    trending_topics = await youtube_service.get_trending_topics(niche)
    
    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "summary": summary,
            "recent_projects": recent_projects,
            "trending_topics": trending_topics,
            "niche": niche,
            "page": "dashboard"
        }
    )
