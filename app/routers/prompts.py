from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
import aiosqlite
import json
from datetime import datetime
from typing import List, Optional
from app.database import get_db
from app.templates import templates

router = APIRouter(prefix="/prompts", tags=["prompts"])

@router.get("", response_class=HTMLResponse)
async def list_prompts(request: Request, category: Optional[str] = None, db: aiosqlite.Connection = Depends(get_db)):
    query = "SELECT * FROM prompts"
    params = []
    if category:
        query += " WHERE category = ?"
        params.append(category)
    query += " ORDER BY category, name ASC"
    
    cursor = await db.execute(query, tuple(params))
    rows = await cursor.fetchall()
    prompts_list = []
    for r in rows:
        p = dict(r)
        p["variables"] = json.loads(p["variables"])
        prompts_list.append(p)
        
    return templates.TemplateResponse(
        "prompts.html",
        {"request": request, "prompts": prompts_list, "category_filter": category, "page": "prompts"}
    )

@router.get("/new", response_class=HTMLResponse)
async def new_prompt_page(request: Request):
    return templates.TemplateResponse(
        "prompt_edit.html",
        {"request": request, "prompt": None, "page": "prompts"}
    )

@router.get("/{prompt_id}", response_class=HTMLResponse)
async def view_prompt(prompt_id: int, request: Request, db: aiosqlite.Connection = Depends(get_db)):
    cursor = await db.execute("SELECT * FROM prompts WHERE id = ?", (prompt_id,))
    row = await cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Prompt template not found")
        
    prompt = dict(row)
    prompt["variables"] = json.loads(prompt["variables"])
    
    return templates.TemplateResponse(
        "prompt_detail.html",
        {"request": request, "prompt": prompt, "page": "prompts"}
    )

@router.get("/{prompt_id}/edit", response_class=HTMLResponse)
async def edit_prompt_page(prompt_id: int, request: Request, db: aiosqlite.Connection = Depends(get_db)):
    cursor = await db.execute("SELECT * FROM prompts WHERE id = ?", (prompt_id,))
    row = await cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Prompt not found")
        
    prompt = dict(row)
    prompt["variables"] = json.loads(prompt["variables"])
    
    return templates.TemplateResponse(
        "prompt_edit.html",
        {"request": request, "prompt": prompt, "page": "prompts"}
    )

@router.post("", response_class=HTMLResponse)
async def create_prompt(
    request: Request,
    name: str = Form(...),
    category: str = Form("general"),
    template_text: str = Form(...),
    variables_raw: str = Form(""), # comma-separated
    description: str = Form(""),
    db: aiosqlite.Connection = Depends(get_db)
):
    variables = [v.strip().upper() for v in variables_raw.split(",") if v.strip()]
    
    await db.execute(
        """
        INSERT INTO prompts (name, category, template_text, variables, description)
        VALUES (?, ?, ?, ?, ?)
        """,
        (name, category, template_text, json.dumps(variables), description)
    )
    await db.commit()
    return RedirectResponse(url="/prompts", status_code=303)

@router.post("/{prompt_id}", response_class=HTMLResponse)
async def update_prompt(
    prompt_id: int,
    request: Request,
    name: str = Form(...),
    category: str = Form("general"),
    template_text: str = Form(...),
    variables_raw: str = Form(""),
    description: str = Form(""),
    db: aiosqlite.Connection = Depends(get_db)
):
    variables = [v.strip().upper() for v in variables_raw.split(",") if v.strip()]
    
    await db.execute(
        """
        UPDATE prompts
        SET name = ?, category = ?, template_text = ?, variables = ?, description = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (name, category, template_text, json.dumps(variables), description, prompt_id)
    )
    await db.commit()
    return RedirectResponse(url=f"/prompts/{prompt_id}", status_code=303)

@router.delete("/{prompt_id}")
async def delete_prompt(prompt_id: int, request: Request, db: aiosqlite.Connection = Depends(get_db)):
    await db.execute("DELETE FROM prompts WHERE id = ?", (prompt_id,))
    await db.commit()
    
    if request.headers.get("HX-Request"):
        return HTMLResponse(status_code=200, headers={"HX-Redirect": "/prompts"})
    return RedirectResponse(url="/prompts", status_code=303)

@router.post("/{prompt_id}/render", response_class=HTMLResponse)
async def render_prompt(prompt_id: int, request: Request, db: aiosqlite.Connection = Depends(get_db)):
    """HTMX endpoint to substitute template variables from form parameters."""
    cursor = await db.execute("SELECT * FROM prompts WHERE id = ?", (prompt_id,))
    row = await cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Prompt not found")
        
    prompt = dict(row)
    template = prompt["template_text"]
    variables = json.loads(prompt["variables"])
    
    # Extract form values
    form_data = await request.form()
    rendered = template
    for var in variables:
        val = form_data.get(f"var_{var}", f"[{var}]")
        rendered = rendered.replace(f"[{var}]", val)
        
    # Increment usage counter
    await db.execute("UPDATE prompts SET usage_count = usage_count + 1 WHERE id = ?", (prompt_id,))
    await db.commit()
    
    return templates.TemplateResponse(
        "components/prompt_rendered.html",
        {"request": request, "rendered_text": rendered}
    )
