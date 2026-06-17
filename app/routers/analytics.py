from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse
import aiosqlite
import json
from typing import Optional
from app.database import get_db
from app.templates import templates
from app.services import analytics_service, project_service

router = APIRouter(prefix="/analytics", tags=["analytics"])

@router.get("", response_class=HTMLResponse)
async def get_analytics_dashboard(request: Request, db: aiosqlite.Connection = Depends(get_db)):
    # 1. Fetch channel-wide aggregate metrics
    summary = await analytics_service.get_channel_summary(db)
    
    # 2. Fetch daily performance arrays for Chart.js
    chart_data = await analytics_service.get_channel_charts(db, days=30)
    
    # 3. Fetch list of individual video performance (published projects with their views, revenue, ctr, and likes)
    cursor = await db.execute(
        """
        SELECT p.id, p.title, p.niche, p.published_at,
               SUM(a.views) as views,
               AVG(a.ctr) as ctr,
               AVG(a.retention_pct) as retention_pct,
               SUM(a.revenue) as revenue
        FROM projects p
        INNER JOIN analytics a ON a.project_id = p.id
        WHERE p.status = 'published'
        GROUP BY p.id
        ORDER BY views DESC
        """
    )
    video_stats = [dict(row) for row in await cursor.fetchall()]
    
    return templates.TemplateResponse(
        "analytics.html",
        {
            "request": request,
            "summary": summary,
            "chart_data": json.dumps(chart_data),
            "video_stats": video_stats,
            "page": "analytics"
        }
    )

@router.get("/videos/{project_id}", response_class=HTMLResponse)
async def get_video_analytics(project_id: int, request: Request, db: aiosqlite.Connection = Depends(get_db)):
    """Renders specific video diagnostic panel, including its retention curve."""
    project = await project_service.get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
        
    # Get aggregated stats for this project
    cursor = await db.execute(
        """
        SELECT 
            SUM(views) as total_views,
            AVG(ctr) as avg_ctr,
            AVG(retention_pct) as avg_retention,
            SUM(revenue) as total_revenue,
            SUM(subscribers_gained) as total_subs,
            SUM(likes) as total_likes,
            SUM(comments) as total_comments
        FROM analytics
        WHERE project_id = ?
        """,
        (project_id,)
    )
    stats_row = await cursor.fetchone()
    stats = dict(stats_row) if stats_row and stats_row["total_views"] is not None else None
    
    # Fetch simulated or real retention curve data
    retention_curve = analytics_service.get_retention_curve(project_id)
    
    return templates.TemplateResponse(
        "analytics_detail.html",
        {
            "request": request,
            "project": project,
            "stats": stats,
            "retention_curve": json.dumps(retention_curve),
            "page": "analytics"
        }
    )
