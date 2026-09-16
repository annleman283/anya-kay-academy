import json
import os
import shutil
import sqlite3
from pathlib import Path

BASE = Path(__file__).parent
DB_PATH = Path(os.getenv("DB_PATH", str(BASE / "lessons.db")))
SOURCE_DB = BASE / "lessons.db"

LESSON_TESTS = {
    "Урок 5. Виды ресниц": [
        ("Какую толщину мы используем в объёмных наращиваниях ?", ["0,07-0,05", "0,15", "0,10"], 0),
        ("На сколько миллиметров искусственная ресница может быть длиннее натуральной?", ["На 2мм", "На 4мм", "На 3мм"], 2),
        ("Можно ли наращивать изгиб Л на вниз растущие ресницы ?", ["Да", "Нет"], 1),
        ("Какой изгиб универсальный?", ["С", "B", "D"], 0),
        ("Какой изгиб создает более выраженный эффект подкручивания/округления ?", ["D", "M", "C"], 0),
    ],
    "Урок 6. Правила наращивания": [
        ("Какой отступ идеальный?", ["0,5 мм", "0,2 мм", "1 мм"], 0),
        ("Какому эффекту направление «Солнышко» подходит больше всего?", ["Лисий", "Беличий", "Кукольный"], 2),
        ("Какому эффекту направление «Наклонное» подходит больше всего?", ["Лисий", "Беличий", "Кукольный"], 0),
        ("Одна из причин образования склеек", ["Неправильно подобранная длина", "Взята большая капля клея, которая не успела просохнуть", "Неправильно приклеен патч"], 1),
    ],
}


def find_lesson(c, wanted):
    row = c.execute("SELECT id,title FROM lessons WHERE title=?", (wanted,)).fetchone()
    if row:
        return row
    key = wanted.lower().replace(" ", "")
    for r in c.execute("SELECT id,title FROM lessons").fetchall():
        if str(r["title"]).lower().replace(" ", "") == key:
            return r
    return None


def repair_test(c, lesson_id, questions):
    existing = c.execute("SELECT id FROM questions WHERE lesson_id=? ORDER BY order_num,id", (lesson_id,)).fetchall()
    for i, (text, options, correct_index) in enumerate(questions, 1):
        payload = json.dumps(options, ensure_ascii=False)
        if i <= len(existing):
            c.execute(
                "UPDATE questions SET question_text=?,options=?,correct_index=?,explanation='',photo_file_id=NULL,order_num=? WHERE id=?",
                (text, payload, correct_index, i, existing[i - 1]["id"]),
            )
        else:
            c.execute(
                "INSERT INTO questions(lesson_id,question_text,options,correct_index,explanation,photo_file_id,order_num) VALUES(?,?,?,?,?,?,?)",
                (lesson_id, text, payload, correct_index, "", None, i),
            )
    if len(existing) > len(questions):
        c.executemany("DELETE FROM questions WHERE id=?", [(r["id"],) for r in existing[len(questions):]])


def main():
    if not DB_PATH.exists():
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        if not SOURCE_DB.exists():
            raise RuntimeError(f"Source DB not found: {SOURCE_DB}")
        shutil.copy2(SOURCE_DB, DB_PATH)
        print(f"safe_data_repair: seeded persistent DB at {DB_PATH}")

    c = sqlite3.connect(str(DB_PATH), timeout=20)
    c.row_factory = sqlite3.Row
    try:
        for title, questions in LESSON_TESTS.items():
            lesson = find_lesson(c, title)
            if not lesson:
                raise RuntimeError(f"Lesson not found: {title}")
            repair_test(c, int(lesson["id"]), questions)
            print(f"safe_data_repair: restored {title} ({len(questions)} questions)")

        c.executescript("""
        CREATE TRIGGER IF NOT EXISTS academy_attempt_reset_relock
        BEFORE DELETE ON attempts
        BEGIN
          UPDATE students
          SET current_lesson_order = MIN(
            current_lesson_order,
            COALESCE((SELECT order_num FROM lessons WHERE id=OLD.lesson_id), current_lesson_order)
          )
          WHERE user_id=OLD.user_id;
        END;
        """)
        c.commit()
        print("safe_data_repair: reset-test relock trigger ready")
    finally:
        c.close()


if __name__ == "__main__":
    main()
