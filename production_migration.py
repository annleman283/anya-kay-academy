import os
import sqlite3
from pathlib import Path

DB_PATH = Path(os.getenv("DB_PATH", "/data/lessons.db"))


def main():
    if not DB_PATH.exists():
        raise RuntimeError(f"Persistent Academy DB not found: {DB_PATH}")

    c = sqlite3.connect(str(DB_PATH), timeout=30)
    c.row_factory = sqlite3.Row
    try:
        # Backfill any real Academy users that were saved in profiles/attempts but
        # never inserted into the legacy students table.
        c.executescript("""
        INSERT OR IGNORE INTO students(user_id, username, full_name, current_lesson_order)
        SELECT user_id, '', full_name, 1 FROM academy_profiles WHERE user_id > 0;

        INSERT OR IGNORE INTO students(user_id, username, full_name, current_lesson_order)
        SELECT DISTINCT user_id, '', '', 1 FROM attempts WHERE user_id > 0;

        DROP TRIGGER IF EXISTS academy_profile_register_student;
        CREATE TRIGGER academy_profile_register_student
        AFTER INSERT ON academy_profiles
        WHEN NEW.user_id > 0
        BEGIN
          INSERT OR IGNORE INTO students(user_id, username, full_name, current_lesson_order)
          VALUES(NEW.user_id, '', NEW.full_name, 1);
          UPDATE students
          SET full_name=NEW.full_name, last_activity=CURRENT_TIMESTAMP
          WHERE user_id=NEW.user_id;
        END;

        DROP TRIGGER IF EXISTS academy_profile_update_student;
        CREATE TRIGGER academy_profile_update_student
        AFTER UPDATE OF full_name ON academy_profiles
        WHEN NEW.user_id > 0
        BEGIN
          INSERT OR IGNORE INTO students(user_id, username, full_name, current_lesson_order)
          VALUES(NEW.user_id, '', NEW.full_name, 1);
          UPDATE students SET full_name=NEW.full_name WHERE user_id=NEW.user_id;
        END;

        DROP TRIGGER IF EXISTS academy_attempt_register_student;
        CREATE TRIGGER academy_attempt_register_student
        BEFORE INSERT ON attempts
        WHEN NEW.user_id > 0
        BEGIN
          INSERT OR IGNORE INTO students(user_id, username, full_name, current_lesson_order)
          VALUES(NEW.user_id, '', '', 1);
        END;

        DROP TRIGGER IF EXISTS academy_pass_unlock_next;
        CREATE TRIGGER academy_pass_unlock_next
        AFTER INSERT ON attempts
        WHEN NEW.passed=1 AND NEW.user_id > 0
        BEGIN
          UPDATE students
          SET current_lesson_order = MAX(
                current_lesson_order,
                COALESCE((SELECT order_num + 1 FROM lessons WHERE id=NEW.lesson_id), current_lesson_order)
              ),
              last_activity=CURRENT_TIMESTAMP
          WHERE user_id=NEW.user_id;
        END;
        """)

        # Repair progress for users who already passed tests before this fix.
        c.execute("""
          UPDATE students
          SET current_lesson_order = MAX(
            current_lesson_order,
            COALESCE((
              SELECT MAX(l.order_num + 1)
              FROM attempts a JOIN lessons l ON l.id=a.lesson_id
              WHERE a.user_id=students.user_id AND a.passed=1
            ), current_lesson_order)
          )
        """)
        c.commit()
        print("production_migration: student registration/progress repaired")
    finally:
        c.close()


if __name__ == "__main__":
    main()
