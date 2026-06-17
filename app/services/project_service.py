import os
import aiosqlite
import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
from app.config import PROJECTS_DIR
from app.database import DEFAULT_PIPELINE_STEPS

async def create_project(db: aiosqlite.Connection, title: str, topic: str, niche: str = "", language: str = "en", voice_preset: str = "guy", duration_target: int = 480, notes: str = "") -> Dict[str, Any]:
    # 1. Insert into projects table
    cursor = await db.execute(
        """
        INSERT INTO projects (title, topic, niche, language, voice_preset, duration_target, notes, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'draft')
        """,
        (title, topic, niche, language, voice_preset, duration_target, notes)
    )
    project_id = cursor.lastrowid
    
    # 2. Create project assets directory: projects/{project_id}
    project_dir = PROJECTS_DIR / str(project_id)
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "scenes").mkdir(parents=True, exist_ok=True)
    
    # Save a metadata notes file or log folder inside
    with open(project_dir / "meta.txt", "w", encoding="utf-8") as f:
        f.write(f"Project ID: {project_id}\nTitle: {title}\nTopic: {topic}\n")

    # 3. Insert 11 pipeline steps
    for step_num, step_name, step_key in DEFAULT_PIPELINE_STEPS:
        # Step 1 "Select Topic" starts as done, others pending
        status = "done" if step_key == "topic_select" else "pending"
        completed_at = datetime.utcnow().isoformat() if step_key == "topic_select" else None
        
        await db.execute(
            """
            INSERT INTO pipeline_steps (project_id, step_number, step_name, step_key, status, completed_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (project_id, step_num, step_name, step_key, status, completed_at)
        )
    
    # 4. Commit changes
    await db.commit()
    
    return await get_project(db, project_id)

async def get_projects(db: aiosqlite.Connection) -> List[Dict[str, Any]]:
    cursor = await db.execute(
        """
        SELECT p.*, 
               (SELECT COUNT(*) FROM pipeline_steps WHERE project_id = p.id AND status = 'done') as completed_steps,
               (SELECT COUNT(*) FROM pipeline_steps WHERE project_id = p.id) as total_steps
        FROM projects p
        ORDER BY p.created_at DESC
        """
    )
    rows = await cursor.fetchall()
    return [dict(row) for row in rows]

async def get_project(db: aiosqlite.Connection, project_id: int) -> Optional[Dict[str, Any]]:
    # Get project row
    cursor = await db.execute("SELECT * FROM projects WHERE id = ?", (project_id,))
    row = await cursor.fetchone()
    if not row:
        return None
    
    project_data = dict(row)
    
    # Get pipeline steps
    cursor = await db.execute("SELECT * FROM pipeline_steps WHERE project_id = ? ORDER BY step_number ASC", (project_id,))
    steps = await cursor.fetchall()
    project_data["pipeline_steps"] = [dict(s) for s in steps]
    
    # Calculate progress percentage
    done_steps = sum(1 for s in project_data["pipeline_steps"] if s["status"] == "done")
    total_steps = len(project_data["pipeline_steps"])
    project_data["progress_pct"] = int((done_steps / total_steps) * 100) if total_steps > 0 else 0
    project_data["completed_steps"] = done_steps
    project_data["total_steps"] = total_steps
    
    # Get artifacts
    cursor = await db.execute("SELECT * FROM artifacts WHERE project_id = ? ORDER BY created_at DESC", (project_id,))
    artifacts = await cursor.fetchall()
    project_data["artifacts"] = [dict(art) for art in artifacts]
    
    return project_data

async def update_project(db: aiosqlite.Connection, project_id: int, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not updates:
        return await get_project(db, project_id)
        
    set_clause = []
    values = []
    for k, v in updates.items():
        set_clause.append(f"{k} = ?")
        values.append(v)
    
    # Update timestamp
    set_clause.append("updated_at = CURRENT_TIMESTAMP")
    values.append(project_id)
    
    query = f"UPDATE projects SET {', '.join(set_clause)} WHERE id = ?"
    await db.execute(query, tuple(values))
    await db.commit()
    
    return await get_project(db, project_id)

async def update_step(db: aiosqlite.Connection, project_id: int, step_key: str, status: str, notes: str = "") -> Optional[Dict[str, Any]]:
    completed_at = datetime.utcnow().isoformat() if status == "done" else None
    
    await db.execute(
        """
        UPDATE pipeline_steps
        SET status = ?, notes = ?, completed_at = ?
        WHERE project_id = ? AND step_key = ?
        """,
        (status, notes, completed_at, project_id, step_key)
    )
    
    # If a step is done, update the project status if necessary
    if step_key == "publish" and status == "done":
        await db.execute(
            "UPDATE projects SET status = 'published', published_at = CURRENT_TIMESTAMP WHERE id = ?",
            (project_id,)
        )
    elif status == "done":
        # Check if the project was in 'draft' and move to 'in_progress'
        cursor = await db.execute("SELECT status FROM projects WHERE id = ?", (project_id,))
        p_row = await cursor.fetchone()
        if p_row and p_row[0] == "draft":
            await db.execute("UPDATE projects SET status = 'in_progress' WHERE id = ?", (project_id,))
            
    await db.commit()
    return await get_project(db, project_id)

async def add_artifact(db: aiosqlite.Connection, project_id: int, artifact_type: str, file_path: str, file_size: int = 0) -> Dict[str, Any]:
    # Check if this file already exists in artifacts to increment version
    cursor = await db.execute(
        "SELECT MAX(version) FROM artifacts WHERE project_id = ? AND type = ?",
        (project_id, artifact_type)
    )
    row = await cursor.fetchone()
    version = (row[0] or 0) + 1 if row else 1
    
    cursor = await db.execute(
        """
        INSERT INTO artifacts (project_id, type, file_path, file_size, version)
        VALUES (?, ?, ?, ?, ?)
        """,
        (project_id, artifact_type, file_path, file_size, version)
    )
    await db.commit()
    
    artifact_id = cursor.lastrowid
    return {
        "id": artifact_id,
        "project_id": project_id,
        "type": artifact_type,
        "file_path": file_path,
        "file_size": file_size,
        "version": version
    }

async def delete_project(db: aiosqlite.Connection, project_id: int) -> bool:
    # 1. Delete DB project (cascade takes care of steps, artifacts, analytics)
    await db.execute("DELETE FROM projects WHERE id = ?", (project_id,))
    await db.commit()
    
    # 2. Try to clean up local folders, but don't crash if they have locks or are already gone
    try:
        project_dir = PROJECTS_DIR / str(project_id)
        if project_dir.exists():
            import shutil
            shutil.rmtree(project_dir)
    except Exception as e:
        print(f"[Project Service] Failed to remove folder for project {project_id}: {e}")
        
    return True
