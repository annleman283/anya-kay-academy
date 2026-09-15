import json
import sqlite3
import threading

from config import DB_PATH, ADMIN_IDS

_lock = threading.Lock()
_conn = sqlite3.connect(DB_PATH, check_same_thread=False)
_conn.row_factory = sqlite3.Row


def _column_exists(table: str, column: str) -> bool:
    rows = _conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(r[1] == column for r in rows)


def _ensure_column(table: str, column: str, coltype_with_default: str):
    if not _column_exists(table, column):
        _conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {coltype_with_default}")


def _migrate_schema():
    """Безопасно дополняет уже существующую базу новыми полями, ничего не удаляя."""
    with _lock, _conn:
        _ensure_column("lessons", "video_type", "TEXT NOT NULL DEFAULT 'file'")
        _ensure_column("lessons", "video_url", "TEXT")
        _ensure_column("questions", "explanation", "TEXT")
        _ensure_column("questions", "photo_file_id", "TEXT")
        _ensure_column("lesson_materials", "file_type", "TEXT NOT NULL DEFAULT 'document'")
        _ensure_column("bonus_materials", "file_type", "TEXT NOT NULL DEFAULT 'document'")
        _ensure_column("students", "last_activity", "TEXT")
        _ensure_column("students", "last_reminder_at", "TEXT")


def init_db():
    with _lock, _conn:
        _conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS lessons (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_num INTEGER UNIQUE NOT NULL,
                title TEXT NOT NULL,
                description TEXT,
                video_type TEXT NOT NULL DEFAULT 'file',   -- 'file' или 'link'
                video_file_id TEXT,
                video_url TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS lesson_materials (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lesson_id INTEGER NOT NULL,
                file_id TEXT NOT NULL,
                file_type TEXT NOT NULL DEFAULT 'document',
                caption TEXT,
                order_num INTEGER NOT NULL,
                FOREIGN KEY (lesson_id) REFERENCES lessons(id)
            );

            CREATE TABLE IF NOT EXISTS bonus_materials (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_id TEXT NOT NULL,
                file_type TEXT NOT NULL DEFAULT 'document',
                caption TEXT,
                order_num INTEGER NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS questions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lesson_id INTEGER NOT NULL,
                question_text TEXT NOT NULL,
                options TEXT NOT NULL,
                correct_index INTEGER NOT NULL,
                explanation TEXT,
                photo_file_id TEXT,
                order_num INTEGER NOT NULL,
                FOREIGN KEY (lesson_id) REFERENCES lessons(id)
            );

            CREATE TABLE IF NOT EXISTS students (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                full_name TEXT,
                current_lesson_order INTEGER DEFAULT 1,
                registered_at TEXT DEFAULT CURRENT_TIMESTAMP,
                last_activity TEXT DEFAULT CURRENT_TIMESTAMP,
                last_reminder_at TEXT
            );

            CREATE TABLE IF NOT EXISTS attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                lesson_id INTEGER NOT NULL,
                attempt_number INTEGER NOT NULL,
                score INTEGER NOT NULL,
                total INTEGER NOT NULL,
                passed INTEGER NOT NULL,
                finished_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS answers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                attempt_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                lesson_id INTEGER NOT NULL,
                question_id INTEGER NOT NULL,
                question_text TEXT NOT NULL,
                chosen_text TEXT NOT NULL,
                correct_text TEXT NOT NULL,
                is_correct INTEGER NOT NULL,
                answered_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (attempt_id) REFERENCES attempts(id)
            );
            """
        )
    _migrate_schema()


# ---------- LESSONS ----------

def add_lesson(title: str, description: str, video_type: str, video_file_id: str, video_url: str) -> int:
    with _lock, _conn:
        row = _conn.execute("SELECT COALESCE(MAX(order_num), 0) + 1 AS n FROM lessons").fetchone()
        next_order = row["n"]
        cur = _conn.execute(
            "INSERT INTO lessons (order_num, title, description, video_type, video_file_id, video_url) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (next_order, title, description, video_type, video_file_id, video_url),
        )
        return cur.lastrowid


def update_lesson_video(lesson_id: int, video_type: str, video_file_id: str, video_url: str):
    with _lock, _conn:
        _conn.execute(
            "UPDATE lessons SET video_type = ?, video_file_id = ?, video_url = ? WHERE id = ?",
            (video_type, video_file_id, video_url, lesson_id),
        )


def update_lesson_text(lesson_id: int, title: str, description: str):
    with _lock, _conn:
        _conn.execute(
            "UPDATE lessons SET title = ?, description = ? WHERE id = ?",
            (title, description, lesson_id),
        )


def get_lesson_by_order(order_num: int):
    with _lock:
        return _conn.execute("SELECT * FROM lessons WHERE order_num = ?", (order_num,)).fetchone()


def get_lesson_by_id(lesson_id: int):
    with _lock:
        return _conn.execute("SELECT * FROM lessons WHERE id = ?", (lesson_id,)).fetchone()


def get_all_lessons():
    with _lock:
        return _conn.execute("SELECT * FROM lessons ORDER BY order_num").fetchall()


def get_max_lesson_order():
    with _lock:
        row = _conn.execute("SELECT COALESCE(MAX(order_num), 0) AS n FROM lessons").fetchone()
        return row["n"]


def delete_lesson(lesson_id: int):
    with _lock, _conn:
        _conn.execute("DELETE FROM questions WHERE lesson_id = ?", (lesson_id,))
        _conn.execute("DELETE FROM lesson_materials WHERE lesson_id = ?", (lesson_id,))
        _conn.execute("DELETE FROM lessons WHERE id = ?", (lesson_id,))


# ---------- LESSON MATERIALS (файлы-пособия к уроку) ----------

def add_lesson_material(lesson_id: int, file_id: str, caption: str, file_type: str = "document") -> int:
    with _lock, _conn:
        row = _conn.execute(
            "SELECT COALESCE(MAX(order_num), 0) + 1 AS n FROM lesson_materials WHERE lesson_id = ?",
            (lesson_id,),
        ).fetchone()
        cur = _conn.execute(
            "INSERT INTO lesson_materials (lesson_id, file_id, file_type, caption, order_num) VALUES (?, ?, ?, ?, ?)",
            (lesson_id, file_id, file_type, caption, row["n"]),
        )
        return cur.lastrowid


def get_materials_for_lesson(lesson_id: int):
    with _lock:
        return _conn.execute(
            "SELECT * FROM lesson_materials WHERE lesson_id = ? ORDER BY order_num", (lesson_id,)
        ).fetchall()


def get_material_by_id(material_id: int):
    with _lock:
        return _conn.execute("SELECT * FROM lesson_materials WHERE id = ?", (material_id,)).fetchone()


def delete_lesson_material(material_id: int):
    with _lock, _conn:
        _conn.execute("DELETE FROM lesson_materials WHERE id = ?", (material_id,))


def update_lesson_material_caption(material_id: int, caption: str):
    with _lock, _conn:
        _conn.execute("UPDATE lesson_materials SET caption = ? WHERE id = ?", (caption, material_id))


def update_lesson_material_file(material_id: int, file_id: str, file_type: str):
    with _lock, _conn:
        _conn.execute(
            "UPDATE lesson_materials SET file_id = ?, file_type = ? WHERE id = ?",
            (file_id, file_type, material_id),
        )


# ---------- BONUS MATERIALS (гайды-подарки) ----------

def add_bonus_material(file_id: str, caption: str, file_type: str = "document") -> int:
    with _lock, _conn:
        row = _conn.execute("SELECT COALESCE(MAX(order_num), 0) + 1 AS n FROM bonus_materials").fetchone()
        cur = _conn.execute(
            "INSERT INTO bonus_materials (file_id, file_type, caption, order_num) VALUES (?, ?, ?, ?)",
            (file_id, file_type, caption, row["n"]),
        )
        return cur.lastrowid


def get_all_bonus_materials():
    with _lock:
        return _conn.execute("SELECT * FROM bonus_materials ORDER BY order_num").fetchall()


def get_bonus_material_by_id(material_id: int):
    with _lock:
        return _conn.execute("SELECT * FROM bonus_materials WHERE id = ?", (material_id,)).fetchone()


def delete_bonus_material(material_id: int):
    with _lock, _conn:
        _conn.execute("DELETE FROM bonus_materials WHERE id = ?", (material_id,))


def update_bonus_material_caption(material_id: int, caption: str):
    with _lock, _conn:
        _conn.execute("UPDATE bonus_materials SET caption = ? WHERE id = ?", (caption, material_id))


def update_bonus_material_file(material_id: int, file_id: str, file_type: str = "document"):
    with _lock, _conn:
        _conn.execute(
            "UPDATE bonus_materials SET file_id = ?, file_type = ? WHERE id = ?",
            (file_id, file_type, material_id),
        )


# ---------- QUESTIONS ----------

def add_question(lesson_id: int, question_text: str, options: list, correct_index: int, explanation: str = "", photo_file_id: str = None) -> int:
    with _lock, _conn:
        row = _conn.execute(
            "SELECT COALESCE(MAX(order_num), 0) + 1 AS n FROM questions WHERE lesson_id = ?", (lesson_id,)
        ).fetchone()
        next_order = row["n"]
        cur = _conn.execute(
            "INSERT INTO questions (lesson_id, question_text, options, correct_index, explanation, photo_file_id, order_num) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (lesson_id, question_text, json.dumps(options, ensure_ascii=False), correct_index, explanation, photo_file_id, next_order),
        )
        return cur.lastrowid


def get_question_by_id(question_id: int):
    with _lock:
        row = _conn.execute("SELECT * FROM questions WHERE id = ?", (question_id,)).fetchone()
    if row is None:
        return None
    d = dict(row)
    d["options"] = json.loads(d["options"])
    return d


def update_question(question_id: int, question_text: str, options: list, correct_index: int, explanation: str = "", photo_file_id: str = None):
    with _lock, _conn:
        _conn.execute(
            "UPDATE questions SET question_text = ?, options = ?, correct_index = ?, explanation = ?, photo_file_id = ? "
            "WHERE id = ?",
            (question_text, json.dumps(options, ensure_ascii=False), correct_index, explanation, photo_file_id, question_id),
        )


def delete_question(question_id: int):
    with _lock, _conn:
        _conn.execute("DELETE FROM questions WHERE id = ?", (question_id,))


def get_questions_for_lesson(lesson_id: int):
    with _lock:
        rows = _conn.execute(
            "SELECT * FROM questions WHERE lesson_id = ? ORDER BY order_num", (lesson_id,)
        ).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        d["options"] = json.loads(d["options"])
        result.append(d)
    return result


# ---------- STUDENTS ----------

def ensure_student(user_id: int, username: str, full_name: str):
    with _lock, _conn:
        row = _conn.execute("SELECT user_id FROM students WHERE user_id = ?", (user_id,)).fetchone()
        if row is None:
            _conn.execute(
                "INSERT INTO students (user_id, username, full_name, current_lesson_order) VALUES (?, ?, ?, 1)",
                (user_id, username, full_name),
            )
            return True  # новая ученица
        else:
            _conn.execute(
                "UPDATE students SET username = ?, full_name = ? WHERE user_id = ?",
                (username, full_name, user_id),
            )
            return False  # уже была зарегистрирована


def get_student(user_id: int):
    with _lock:
        return _conn.execute("SELECT * FROM students WHERE user_id = ?", (user_id,)).fetchone()


def get_all_students():
    """Список учениц, БЕЗ учёта админов (чтобы тестовые заходы админа не путались со статистикой)."""
    with _lock:
        rows = _conn.execute("SELECT * FROM students ORDER BY registered_at DESC").fetchall()
    if not ADMIN_IDS:
        return rows
    return [r for r in rows if r["user_id"] not in ADMIN_IDS]


def unlock_next_lesson(user_id: int, passed_order: int):
    with _lock, _conn:
        row = _conn.execute(
            "SELECT current_lesson_order FROM students WHERE user_id = ?", (user_id,)
        ).fetchone()
        if row and row["current_lesson_order"] <= passed_order:
            _conn.execute(
                "UPDATE students SET current_lesson_order = ? WHERE user_id = ?",
                (passed_order + 1, user_id),
            )


def reset_student_progress(user_id: int):
    """Сбросить прогресс (для тестового режима админа)."""
    with _lock, _conn:
        _conn.execute(
            "UPDATE students SET current_lesson_order = 1 WHERE user_id = ?", (user_id,)
        )
        _conn.execute("DELETE FROM answers WHERE user_id = ?", (user_id,))
        _conn.execute("DELETE FROM attempts WHERE user_id = ?", (user_id,))


def touch_activity(user_id: int):
    with _lock, _conn:
        _conn.execute(
            "UPDATE students SET last_activity = CURRENT_TIMESTAMP WHERE user_id = ?",
            (user_id,),
        )


def get_inactive_students(days: int):
    with _lock:
        max_order = _conn.execute("SELECT COALESCE(MAX(order_num), 0) AS n FROM lessons").fetchone()["n"]
        rows = _conn.execute(
            """
            SELECT * FROM students
            WHERE current_lesson_order <= ?
              AND datetime(last_activity) <= datetime('now', ?)
              AND (last_reminder_at IS NULL OR datetime(last_reminder_at) < datetime(last_activity))
            """,
            (max_order, f"-{days} days"),
        ).fetchall()
    if not ADMIN_IDS:
        return rows
    return [r for r in rows if r["user_id"] not in ADMIN_IDS]


def mark_reminded(user_id: int):
    with _lock, _conn:
        _conn.execute(
            "UPDATE students SET last_reminder_at = CURRENT_TIMESTAMP WHERE user_id = ?",
            (user_id,),
        )


# ---------- ATTEMPTS / ANSWERS ----------

def next_attempt_number(user_id: int, lesson_id: int) -> int:
    with _lock:
        row = _conn.execute(
            "SELECT COALESCE(MAX(attempt_number), 0) + 1 AS n FROM attempts WHERE user_id = ? AND lesson_id = ?",
            (user_id, lesson_id),
        ).fetchone()
        return row["n"]


def save_attempt(user_id: int, lesson_id: int, attempt_number: int, answers: list, score: int, total: int, passed: bool) -> int:
    with _lock, _conn:
        cur = _conn.execute(
            "INSERT INTO attempts (user_id, lesson_id, attempt_number, score, total, passed) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, lesson_id, attempt_number, score, total, int(passed)),
        )
        attempt_id = cur.lastrowid
        for a in answers:
            _conn.execute(
                "INSERT INTO answers (attempt_id, user_id, lesson_id, question_id, question_text, "
                "chosen_text, correct_text, is_correct) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    attempt_id, user_id, lesson_id, a["question_id"], a["question_text"],
                    a["chosen_text"], a["correct_text"], int(a["is_correct"]),
                ),
            )
        return attempt_id


def get_attempts_for_student(user_id: int):
    with _lock:
        return _conn.execute(
            "SELECT * FROM attempts WHERE user_id = ? ORDER BY finished_at", (user_id,)
        ).fetchall()


def get_answers_for_attempt(attempt_id: int):
    with _lock:
        return _conn.execute(
            "SELECT * FROM answers WHERE attempt_id = ? ORDER BY id", (attempt_id,)
        ).fetchall()
