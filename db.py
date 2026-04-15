import json
import os
import sqlite3
import logging
from datetime import datetime, timezone

from config import DB_PATH, DATA_DIR

logger = logging.getLogger(__name__)

os.makedirs(DATA_DIR, exist_ok=True)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    name TEXT NOT NULL,
    max_iterations INTEGER NOT NULL DEFAULT 50,
    used_iterations INTEGER NOT NULL DEFAULT 0,
    max_videos INTEGER NOT NULL DEFAULT 5,
    used_videos INTEGER NOT NULL DEFAULT 0,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS scripts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    text TEXT NOT NULL,
    language TEXT NOT NULL DEFAULT 'fil-PH',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS generations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    script_id INTEGER,
    method TEXT NOT NULL,
    voice TEXT,
    params_json TEXT,
    audio_file TEXT,
    format TEXT DEFAULT 'wav',
    text_output TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (script_id) REFERENCES scripts(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS video_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    sora_video_id TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    progress INTEGER DEFAULT 0,
    script TEXT,
    generated_prompt TEXT,
    style TEXT,
    resolution TEXT,
    has_reference_image INTEGER DEFAULT 0,
    video_file TEXT,
    error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS video_projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'planning',
    script TEXT NOT NULL,
    style TEXT NOT NULL DEFAULT 'animation',
    resolution TEXT NOT NULL DEFAULT '1280x720',
    total_scenes INTEGER DEFAULT 0,
    completed_scenes INTEGER DEFAULT 0,
    final_video_file TEXT,
    error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS video_scenes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    scene_number INTEGER NOT NULL,
    description TEXT,
    prompt TEXT,
    duration INTEGER DEFAULT 12,
    sora_video_id TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    progress INTEGER DEFAULT 0,
    video_file TEXT,
    error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (project_id) REFERENCES video_projects(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS avatars (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    name TEXT NOT NULL,
    description TEXT,
    source TEXT NOT NULL DEFAULT 'text',
    model_used TEXT,
    landscape_file TEXT,
    portrait_file TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id)
);
"""


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    conn = _get_conn()
    conn.executescript(_SCHEMA)
    conn.commit()

    # Seed built-in avatars if not present
    existing = conn.execute("SELECT COUNT(*) as cnt FROM avatars WHERE user_id IS NULL").fetchone()
    if existing["cnt"] == 0:
        from config import AVATARS
        now = datetime.now(timezone.utc).isoformat()
        for av in AVATARS:
            # Extract just the filename from the path
            land = av["landscape_file"].split("/")[-1]
            port = av["portrait_file"].split("/")[-1]
            conn.execute(
                "INSERT INTO avatars (user_id, name, description, source, model_used, landscape_file, portrait_file, created_at) "
                "VALUES (NULL, ?, ?, 'builtin', 'gpt-image-1', ?, ?, ?)",
                (av["name"], av["description"], land, port, now),
            )
        conn.commit()
        logger.info(f"Seeded {len(AVATARS)} built-in avatars")

    conn.close()
    logger.info(f"Database initialized at {DB_PATH}")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# --- Scripts CRUD ---

def create_script(title: str, text: str, language: str = "fil-PH") -> dict:
    now = _now()
    conn = _get_conn()
    cursor = conn.execute(
        "INSERT INTO scripts (title, text, language, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
        (title, text, language, now, now),
    )
    conn.commit()
    script_id = cursor.lastrowid
    conn.close()
    return {"id": script_id, "title": title, "text": text, "language": language, "created_at": now, "updated_at": now}


def get_script(script_id: int) -> dict | None:
    conn = _get_conn()
    row = conn.execute("SELECT * FROM scripts WHERE id = ?", (script_id,)).fetchone()
    if not row:
        conn.close()
        return None
    script = dict(row)
    generations = conn.execute(
        "SELECT * FROM generations WHERE script_id = ? ORDER BY created_at DESC", (script_id,)
    ).fetchall()
    script["generations"] = [dict(g) for g in generations]
    conn.close()
    return script


def list_scripts() -> list[dict]:
    conn = _get_conn()
    rows = conn.execute("SELECT * FROM scripts ORDER BY updated_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_script(script_id: int, title: str | None = None, text: str | None = None, language: str | None = None) -> dict | None:
    conn = _get_conn()
    row = conn.execute("SELECT * FROM scripts WHERE id = ?", (script_id,)).fetchone()
    if not row:
        conn.close()
        return None
    updates = {}
    if title is not None:
        updates["title"] = title
    if text is not None:
        updates["text"] = text
    if language is not None:
        updates["language"] = language
    if not updates:
        conn.close()
        return dict(row)
    updates["updated_at"] = _now()
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [script_id]
    conn.execute(f"UPDATE scripts SET {set_clause} WHERE id = ?", values)
    conn.commit()
    updated = conn.execute("SELECT * FROM scripts WHERE id = ?", (script_id,)).fetchone()
    conn.close()
    return dict(updated)


def delete_script(script_id: int) -> bool:
    conn = _get_conn()
    cursor = conn.execute("DELETE FROM scripts WHERE id = ?", (script_id,))
    conn.commit()
    conn.close()
    return cursor.rowcount > 0


# --- Generations ---

def record_generation(
    method: str,
    voice: str | None = None,
    params: dict | None = None,
    audio_file: str | None = None,
    fmt: str = "wav",
    text_output: str | None = None,
    script_id: int | None = None,
) -> dict:
    now = _now()
    params_json = json.dumps(params) if params else None
    conn = _get_conn()
    cursor = conn.execute(
        "INSERT INTO generations (script_id, method, voice, params_json, audio_file, format, text_output, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (script_id, method, voice, params_json, audio_file, fmt, text_output, now),
    )
    conn.commit()
    gen_id = cursor.lastrowid
    conn.close()
    return {"id": gen_id, "script_id": script_id, "method": method, "created_at": now}


# --- Users ---

def create_user(username: str, password: str, name: str, max_iterations: int = 50, max_videos: int = 5) -> dict:
    from werkzeug.security import generate_password_hash
    now = _now()
    conn = _get_conn()
    try:
        cursor = conn.execute(
            "INSERT INTO users (username, password_hash, name, max_iterations, used_iterations, max_videos, used_videos, active, created_at) VALUES (?, ?, ?, ?, 0, ?, 0, 1, ?)",
            (username, generate_password_hash(password), name, max_iterations, max_videos, now),
        )
        conn.commit()
        user_id = cursor.lastrowid
    except sqlite3.IntegrityError:
        conn.close()
        raise ValueError(f"Username '{username}' already exists")
    conn.close()
    return {"id": user_id, "username": username, "name": name, "max_iterations": max_iterations, "max_videos": max_videos}


def verify_user(username: str, password: str) -> dict | None:
    from werkzeug.security import check_password_hash
    conn = _get_conn()
    row = conn.execute("SELECT * FROM users WHERE username = ? AND active = 1", (username,)).fetchone()
    conn.close()
    if not row:
        return None
    user = dict(row)
    if not check_password_hash(user["password_hash"], password):
        return None
    del user["password_hash"]
    return user


def get_user_by_id(user_id: int) -> dict | None:
    conn = _get_conn()
    row = conn.execute("SELECT id, username, name, max_iterations, used_iterations, max_videos, used_videos, active, created_at FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def increment_user_iterations(user_id: int) -> dict | None:
    conn = _get_conn()
    conn.execute("UPDATE users SET used_iterations = used_iterations + 1 WHERE id = ?", (user_id,))
    conn.commit()
    row = conn.execute("SELECT id, username, name, max_iterations, used_iterations FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def check_user_quota(user_id: int) -> bool:
    conn = _get_conn()
    row = conn.execute("SELECT max_iterations, used_iterations FROM users WHERE id = ? AND active = 1", (user_id,)).fetchone()
    conn.close()
    if not row:
        return False
    return row["used_iterations"] < row["max_iterations"]


def check_user_video_quota(user_id: int) -> bool:
    conn = _get_conn()
    row = conn.execute("SELECT max_videos, used_videos FROM users WHERE id = ? AND active = 1", (user_id,)).fetchone()
    conn.close()
    if not row:
        return False
    return row["used_videos"] < row["max_videos"]


def increment_user_videos(user_id: int):
    conn = _get_conn()
    conn.execute("UPDATE users SET used_videos = used_videos + 1 WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()


# --- Video Jobs ---

def create_video_job(user_id: int, script: str, generated_prompt: str, style: str, resolution: str, has_ref: bool) -> dict:
    now = _now()
    conn = _get_conn()
    cursor = conn.execute(
        "INSERT INTO video_jobs (user_id, status, script, generated_prompt, style, resolution, has_reference_image, created_at, updated_at) VALUES (?, 'pending', ?, ?, ?, ?, ?, ?, ?)",
        (user_id, script, generated_prompt, style, resolution, 1 if has_ref else 0, now, now),
    )
    conn.commit()
    job_id = cursor.lastrowid
    conn.close()
    return {"id": job_id, "status": "pending", "created_at": now}


def update_video_job(job_id: int, **kwargs) -> None:
    conn = _get_conn()
    kwargs["updated_at"] = _now()
    set_clause = ", ".join(f"{k} = ?" for k in kwargs)
    values = list(kwargs.values()) + [job_id]
    conn.execute(f"UPDATE video_jobs SET {set_clause} WHERE id = ?", values)
    conn.commit()
    conn.close()


def get_video_job(job_id: int) -> dict | None:
    conn = _get_conn()
    row = conn.execute("SELECT * FROM video_jobs WHERE id = ?", (job_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_user_video_jobs(user_id: int) -> list[dict]:
    conn = _get_conn()
    rows = conn.execute("SELECT * FROM video_jobs WHERE user_id = ? ORDER BY created_at DESC LIMIT 20", (user_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# --- Video Projects (Storyboard) ---

def create_video_project(user_id: int, script: str, style: str, resolution: str) -> dict:
    now = _now()
    conn = _get_conn()
    cursor = conn.execute(
        "INSERT INTO video_projects (user_id, status, script, style, resolution, created_at, updated_at) VALUES (?, 'planning', ?, ?, ?, ?, ?)",
        (user_id, script, style, resolution, now, now),
    )
    conn.commit()
    pid = cursor.lastrowid
    conn.close()
    return {"id": pid, "status": "planning", "created_at": now}


def add_project_scenes(project_id: int, scenes: list[dict]) -> list[dict]:
    now = _now()
    conn = _get_conn()
    result = []
    for s in scenes:
        cursor = conn.execute(
            "INSERT INTO video_scenes (project_id, scene_number, description, prompt, duration, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)",
            (project_id, s["scene_number"], s.get("description", ""), s.get("prompt", ""), s.get("duration", 12), now, now),
        )
        result.append({"id": cursor.lastrowid, "scene_number": s["scene_number"]})
    conn.execute("UPDATE video_projects SET total_scenes = ?, status = 'ready', updated_at = ? WHERE id = ?",
                 (len(scenes), now, project_id))
    conn.commit()
    conn.close()
    return result


def get_video_project(project_id: int) -> dict | None:
    conn = _get_conn()
    row = conn.execute("SELECT * FROM video_projects WHERE id = ?", (project_id,)).fetchone()
    if not row:
        conn.close()
        return None
    project = dict(row)
    scenes = conn.execute("SELECT * FROM video_scenes WHERE project_id = ? ORDER BY scene_number", (project_id,)).fetchall()
    project["scenes"] = [dict(s) for s in scenes]
    conn.close()
    return project


def get_user_video_projects(user_id: int) -> list[dict]:
    conn = _get_conn()
    rows = conn.execute("SELECT * FROM video_projects WHERE user_id = ? ORDER BY created_at DESC LIMIT 20", (user_id,)).fetchall()
    projects = []
    for r in rows:
        p = dict(r)
        scenes = conn.execute("SELECT id, scene_number, status, progress, description FROM video_scenes WHERE project_id = ? ORDER BY scene_number", (p["id"],)).fetchall()
        p["scenes"] = [dict(s) for s in scenes]
        projects.append(p)
    conn.close()
    return projects


def update_video_scene(scene_id: int, **kwargs) -> None:
    conn = _get_conn()
    kwargs["updated_at"] = _now()
    set_clause = ", ".join(f"{k} = ?" for k in kwargs)
    values = list(kwargs.values()) + [scene_id]
    conn.execute(f"UPDATE video_scenes SET {set_clause} WHERE id = ?", values)
    conn.commit()
    conn.close()


def update_video_project(project_id: int, **kwargs) -> None:
    conn = _get_conn()
    kwargs["updated_at"] = _now()
    set_clause = ", ".join(f"{k} = ?" for k in kwargs)
    values = list(kwargs.values()) + [project_id]
    conn.execute(f"UPDATE video_projects SET {set_clause} WHERE id = ?", values)
    conn.commit()
    conn.close()


def count_completed_scenes(project_id: int) -> int:
    conn = _get_conn()
    row = conn.execute("SELECT COUNT(*) as cnt FROM video_scenes WHERE project_id = ? AND status = 'completed'", (project_id,)).fetchone()
    conn.close()
    return row["cnt"] if row else 0


def get_project_scene_files(project_id: int) -> list[str]:
    conn = _get_conn()
    rows = conn.execute("SELECT video_file FROM video_scenes WHERE project_id = ? AND status = 'completed' ORDER BY scene_number", (project_id,)).fetchall()
    conn.close()
    return [r["video_file"] for r in rows if r["video_file"]]


# --- Avatars ---

def create_avatar(user_id: int | None, name: str, description: str, source: str, model_used: str,
                  landscape_file: str, portrait_file: str) -> dict:
    now = _now()
    conn = _get_conn()
    cursor = conn.execute(
        "INSERT INTO avatars (user_id, name, description, source, model_used, landscape_file, portrait_file, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (user_id, name, description, source, model_used, landscape_file, portrait_file, now),
    )
    conn.commit()
    aid = cursor.lastrowid
    conn.close()
    return {"id": aid, "name": name, "source": source, "created_at": now}


def get_all_avatars(user_id: int | None = None) -> list[dict]:
    """Get built-in avatars + user's avatars."""
    conn = _get_conn()
    if user_id:
        rows = conn.execute(
            "SELECT * FROM avatars WHERE user_id IS NULL OR user_id = ? ORDER BY user_id IS NULL DESC, created_at DESC",
            (user_id,),
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM avatars ORDER BY created_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_avatar(avatar_id: int, user_id: int) -> bool:
    """Only delete user-created avatars (not built-in)."""
    conn = _get_conn()
    cursor = conn.execute("DELETE FROM avatars WHERE id = ? AND user_id = ?", (avatar_id, user_id))
    conn.commit()
    conn.close()
    return cursor.rowcount > 0


def get_avatar(avatar_id: int) -> dict | None:
    conn = _get_conn()
    row = conn.execute("SELECT * FROM avatars WHERE id = ?", (avatar_id,)).fetchone()
    conn.close()
    return dict(row) if row else None
