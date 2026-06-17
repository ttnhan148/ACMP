import aiosqlite
import json
import os
from pathlib import Path
from app.config import DB_PATH, SEED_DIR

SCHEMA_VERSION = 1

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS projects (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    title           TEXT NOT NULL,
    topic           TEXT NOT NULL,
    niche           TEXT DEFAULT '',
    language        TEXT DEFAULT 'en',
    status          TEXT DEFAULT 'draft'
                    CHECK(status IN ('draft','in_progress','completed',
                                     'published','abandoned')),
    voice_preset    TEXT DEFAULT 'guy',
    duration_target INTEGER DEFAULT 480,   -- seconds
    youtube_url     TEXT DEFAULT '',
    youtube_video_id TEXT DEFAULT '',
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    published_at    DATETIME,
    notes           TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS pipeline_steps (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id      INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    step_number     INTEGER NOT NULL,
    step_name       TEXT NOT NULL,
    step_key        TEXT NOT NULL,
    status          TEXT DEFAULT 'pending'
                    CHECK(status IN ('pending','in_progress','done','skipped')),
    completed_at    DATETIME,
    notes           TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_steps_project ON pipeline_steps(project_id);

CREATE TABLE IF NOT EXISTS artifacts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id      INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    type            TEXT NOT NULL
                    CHECK(type IN ('script','voice','scene_image','thumbnail',
                                   'video','metadata','notes','other')),
    file_path       TEXT NOT NULL,
    file_size       INTEGER DEFAULT 0,
    version         INTEGER DEFAULT 1,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_artifacts_project ON artifacts(project_id);

CREATE TABLE IF NOT EXISTS prompts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,
    category        TEXT DEFAULT 'general'
                    CHECK(category IN ('research','script','visual','seo',
                                       'compliance','analysis','system','general')),
    template_text   TEXT NOT NULL,
    variables       TEXT DEFAULT '[]',   -- JSON array of variable names
    description     TEXT DEFAULT '',
    usage_count     INTEGER DEFAULT 0,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS analytics (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id      INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    date_collected  DATE NOT NULL,
    views           INTEGER DEFAULT 0,
    ctr             REAL DEFAULT 0.0,
    retention_pct   REAL DEFAULT 0.0,
    rpm             REAL DEFAULT 0.0,
    revenue         REAL DEFAULT 0.0,
    subscribers_gained INTEGER DEFAULT 0,
    likes           INTEGER DEFAULT 0,
    comments        INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_analytics_project ON analytics(project_id);

CREATE TABLE IF NOT EXISTS tasks (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id      INTEGER REFERENCES projects(id) ON DELETE SET NULL,
    task_type       TEXT NOT NULL
                    CHECK(task_type IN ('voice_gen','assembly','seo_gen',
                                        'thumbnail_gen','compliance_check')),
    status          TEXT DEFAULT 'queued'
                    CHECK(status IN ('queued','running','done','failed')),
    progress_pct    INTEGER DEFAULT 0,
    started_at      DATETIME,
    completed_at    DATETIME,
    error_log       TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS settings (
    key             TEXT PRIMARY KEY,
    value           TEXT DEFAULT ''
);
"""

DEFAULT_PIPELINE_STEPS = [
    (1,  "Select Topic",       "topic_select"),
    (2,  "Research",           "research"),
    (3,  "Write Script",       "script"),
    (4,  "Generate Voice",     "voice"),
    (5,  "Create Images",      "images"),
    (6,  "Assemble Video",     "assembly"),
    (7,  "Create Thumbnail",   "thumbnail"),
    (8,  "SEO Metadata",       "seo"),
    (9,  "Compliance Check",   "compliance"),
    (10, "Publish",            "publish"),
    (11, "Track Performance",  "tracking"),
]

async def get_db():
    """FastAPI dependency yielding an active connection with Row factory enabled."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        db.row_factory = aiosqlite.Row
        yield db

async def init_db():
    """Initializes schema and runs migrations on app startup."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        
        # Check database schema version
        cursor = await db.execute("PRAGMA user_version")
        row = await cursor.fetchone()
        version = row[0] if row else 0

        if version < SCHEMA_VERSION:
            print(f"[DB] Initializing database (current version: {version})")
            await db.executescript(SCHEMA_SQL)
            
            # Seed default system settings
            default_settings = [
                ('channel_name', ''),
                ('default_niche', 'history'),
                ('default_language', 'en'),
                ('default_voice', 'guy'),
                ('default_duration', '480'),
                ('projects_dir', './projects'),
                ('ffmpeg_path', 'ffmpeg'),
                ('auto_backup', 'true')
            ]
            for key, val in default_settings:
                await db.execute(
                    "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
                    (key, val)
                )
            
            # Seed default prompts from prompts.json file
            prompts_file = SEED_DIR / "prompts.json"
            if prompts_file.exists():
                try:
                    with open(prompts_file, 'r', encoding='utf-8') as f:
                        prompts_data = json.load(f)
                    for p in prompts_data:
                        await db.execute(
                            """
                            INSERT OR IGNORE INTO prompts (name, category, template_text, variables, description)
                            VALUES (?, ?, ?, ?, ?)
                            """,
                            (
                                p['name'],
                                p['category'],
                                p['template_text'],
                                json.dumps(p['variables']),
                                p['description']
                            )
                        )
                except Exception as e:
                    print(f"[DB] Error seeding default prompts: {e}")
            
            # Update DB version
            await db.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            await db.commit()
            print(f"[DB] Database successfully migrated to version {SCHEMA_VERSION}")
