from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime

# Project Models
class ProjectBase(BaseModel):
    title: str
    topic: str
    niche: Optional[str] = ""
    language: Optional[str] = "en"
    voice_preset: Optional[str] = "guy"
    duration_target: Optional[int] = 480
    notes: Optional[str] = ""

class ProjectCreate(ProjectBase):
    pass

class ProjectUpdate(BaseModel):
    title: Optional[str] = None
    topic: Optional[str] = None
    niche: Optional[str] = None
    language: Optional[str] = None
    status: Optional[str] = None  # draft, in_progress, completed, published, abandoned
    voice_preset: Optional[str] = None
    duration_target: Optional[int] = None
    youtube_url: Optional[str] = None
    youtube_video_id: Optional[str] = None
    published_at: Optional[datetime] = None
    notes: Optional[str] = None

class ProjectResponse(ProjectBase):
    id: int
    status: str
    youtube_url: str
    youtube_video_id: str
    created_at: datetime
    updated_at: datetime
    published_at: Optional[datetime] = None

    class Config:
        from_attributes = True

# Pipeline Step Models
class PipelineStepBase(BaseModel):
    status: str  # pending, in_progress, done, skipped
    notes: Optional[str] = ""

class PipelineStepUpdate(PipelineStepBase):
    completed_at: Optional[datetime] = None

class PipelineStepResponse(PipelineStepBase):
    id: int
    project_id: int
    step_number: int
    step_name: str
    step_key: str
    completed_at: Optional[datetime] = None

    class Config:
        from_attributes = True

# Prompt Models
class PromptBase(BaseModel):
    name: str
    category: str  # research, script, visual, seo, compliance, analysis, system, general
    template_text: str
    variables: List[str] = Field(default_factory=list)
    description: Optional[str] = ""

class PromptCreate(PromptBase):
    pass

class PromptUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    template_text: Optional[str] = None
    variables: Optional[List[str]] = None
    description: Optional[str] = None

class PromptResponse(PromptBase):
    id: int
    usage_count: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

# Artifact Models
class ArtifactBase(BaseModel):
    project_id: int
    type: str  # script, voice, scene_image, thumbnail, video, metadata, notes, other
    file_path: str
    file_size: Optional[int] = 0
    version: Optional[int] = 1

class ArtifactResponse(ArtifactBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True

# Analytics Models
class AnalyticsBase(BaseModel):
    project_id: int
    date_collected: str  # YYYY-MM-DD
    views: Optional[int] = 0
    ctr: Optional[float] = 0.0
    retention_pct: Optional[float] = 0.0
    rpm: Optional[float] = 0.0
    revenue: Optional[float] = 0.0
    subscribers_gained: Optional[int] = 0
    likes: Optional[int] = 0
    comments: Optional[int] = 0

class AnalyticsResponse(AnalyticsBase):
    id: int

    class Config:
        from_attributes = True

# Task Models
class TaskBase(BaseModel):
    project_id: Optional[int] = None
    task_type: str  # voice_gen, assembly, seo_gen, thumbnail_gen, compliance_check
    status: str  # queued, running, done, failed
    progress_pct: Optional[int] = 0
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_log: Optional[str] = ""

class TaskResponse(TaskBase):
    id: int

    class Config:
        from_attributes = True

# Settings Model
class SettingItem(BaseModel):
    key: str
    value: str
