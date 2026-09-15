from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
    WebAppInfo,
)

import config

# ---------- Постоянные меню внизу экрана (ReplyKeyboardMarkup) ----------

STUDENT_MENU_LESSONS = "📚 Все уроки"
STUDENT_MENU_PROGRESS = "📊 Мой прогресс"
STUDENT_MENU_GUIDES = "🎁 Мои гайды"
STUDENT_MENU_HELP = "ℹ️ Помощь"

ADMIN_MENU_ADD_LESSON = "➕ Добавить урок"
ADMIN_MENU_LESSONS = "📚 Мои уроки"
ADMIN_MENU_GUIDES = "🎁 Гайды"
ADMIN_MENU_STUDENTS = "👩‍🎓 Ученицы"
ADMIN_MENU_BACKUP = "💾 Резервная копия"
ADMIN_MENU_TEST_MODE = "🔄 Проверить как ученица (сбросить)"


def _academy_row():
    if not config.ACADEMY_URL:
        return []
    return [KeyboardButton("Открыть Academy", web_app=WebAppInfo(url=config.ACADEMY_URL))]


def student_menu():
    rows = [
        [KeyboardButton(STUDENT_MENU_LESSONS), KeyboardButton(STUDENT_MENU_PROGRESS)],
        [KeyboardButton(STUDENT_MENU_GUIDES), KeyboardButton(STUDENT_MENU_HELP)],
    ]
    academy = _academy_row()
    if academy:
        rows.append(academy)
    return ReplyKeyboardMarkup(
        rows,
        resize_keyboard=True,
        is_persistent=True,
    )


def admin_menu():
    rows = [
        [KeyboardButton(ADMIN_MENU_ADD_LESSON), KeyboardButton(ADMIN_MENU_LESSONS)],
        [KeyboardButton(ADMIN_MENU_GUIDES), KeyboardButton(ADMIN_MENU_STUDENTS)],
        [KeyboardButton(ADMIN_MENU_BACKUP), KeyboardButton(ADMIN_MENU_TEST_MODE)],
    ]
    academy = _academy_row()
    if academy:
        rows.append(academy)
    return ReplyKeyboardMarkup(
        rows,
        resize_keyboard=True,
        is_persistent=True,
    )


# ---------- Inline-клавиатуры ----------

def welcome_kb():
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("▶️ Начать урок 1", callback_data="begin_learning")]]
    )


def lesson_kb(lesson_id: int):
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("📝 Начать тест", callback_data=f"start_quiz:{lesson_id}")]]
    )


def question_kb(lesson_id: int, question_id: int, options: list):
    buttons = []
    for i in range(len(options)):
        buttons.append([InlineKeyboardButton(f"Вариант {i + 1}", callback_data=f"ans:{lesson_id}:{question_id}:{i}")])
    return InlineKeyboardMarkup(buttons)


def retry_kb(lesson_id: int):
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🔁 Попробовать снова", callback_data=f"start_quiz:{lesson_id}")],
            [InlineKeyboardButton("📹 Пересмотреть урок", callback_data=f"rewatch:{lesson_id}")],
        ]
    )


def next_lesson_kb():
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("➡️ Следующий урок", callback_data="next_lesson")]]
    )


def all_lessons_kb(lessons, current_order):
    buttons = []
    for l in lessons:
        if l["order_num"] < current_order:
            icon = "✅"
        elif l["order_num"] == current_order:
            icon = "▶️"
        else:
            icon = "🔒"
        buttons.append(
            [InlineKeyboardButton(f"{icon} {l['title']}", callback_data=f"open_lesson:{l['order_num']}")]
        )
    return InlineKeyboardMarkup(buttons)


def confirm_kb(yes_data: str, no_data: str):
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("✅ Да", callback_data=yes_data)],
            [InlineKeyboardButton("❌ Отмена", callback_data=no_data)],
        ]
    )


# ---------- Клавиатуры админ-диалога добавления урока ----------

def skip_kb(callback_data: str):
    return InlineKeyboardMarkup([[InlineKeyboardButton("⏭ Пропустить", callback_data=callback_data)]])


def photo_choice_kb():
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📷 Прикрепить фото", callback_data="add_q_photo")],
            [InlineKeyboardButton("➡️ Без фото", callback_data="skip_q_photo")],
        ]
    )


def video_choice_kb():
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📁 Загрузить файлом (до 50 МБ)", callback_data="vid_file")],
            [InlineKeyboardButton("🔗 Прислать ссылку (YouTube и т.п.)", callback_data="vid_link")],
        ]
    )


def materials_menu_kb():
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📎 Прикрепить файл", callback_data="add_material")],
            [InlineKeyboardButton("🔗 Прикрепить ссылку", callback_data="add_material_link")],
            [InlineKeyboardButton("➡️ Дальше, к вопросам", callback_data="materials_done")],
        ]
    )


def correct_option_kb(options: list):
    buttons = []
    for i in range(len(options)):
        buttons.append([InlineKeyboardButton(f"Вариант {i + 1}", callback_data=f"correct:{i}")])
    return InlineKeyboardMarkup(buttons)


def question_menu_kb():
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("➕ Следующий вопрос", callback_data="more_question")],
            [InlineKeyboardButton("✅ Завершить урок", callback_data="finish_lesson")],
        ]
    )


# ---------- Управление существующими уроками ----------

def lessons_list_admin_kb(lessons):
    buttons = [
        [InlineKeyboardButton(l["title"], callback_data=f"manage_lesson:{l['id']}")]
        for l in lessons
    ]
    return InlineKeyboardMarkup(buttons)


def manage_lesson_kb(lesson_id: int):
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("👁 Предпросмотр", callback_data=f"preview_lesson:{lesson_id}")],
            [InlineKeyboardButton("🎬 Заменить видео", callback_data=f"replace_video:{lesson_id}")],
            [InlineKeyboardButton("✏️ Название/описание", callback_data=f"edit_title:{lesson_id}")],
            [InlineKeyboardButton("📎 Файлы урока", callback_data=f"manage_materials:{lesson_id}")],
            [InlineKeyboardButton("❓ Вопросы урока", callback_data=f"manage_questions:{lesson_id}")],
            [InlineKeyboardButton("🗑 Удалить урок", callback_data=f"delete_lesson:{lesson_id}")],
            [InlineKeyboardButton("⬅️ Назад к списку", callback_data="back_to_lessons")],
        ]
    )


def questions_manage_kb(questions, lesson_id: int):
    buttons = []
    for q in questions:
        label = q["question_text"][:35] + ("..." if len(q["question_text"]) > 35 else "")
        buttons.append(
            [
                InlineKeyboardButton(f"✏️ {label}", callback_data=f"edit_question:{q['id']}"),
                InlineKeyboardButton("🗑", callback_data=f"delete_question:{q['id']}:{lesson_id}"),
            ]
        )
    buttons.append([InlineKeyboardButton("➕ Добавить вопрос", callback_data=f"add_question_existing:{lesson_id}")])
    buttons.append([InlineKeyboardButton("⬅️ Назад", callback_data=f"manage_lesson:{lesson_id}")])
    return InlineKeyboardMarkup(buttons)


def materials_manage_kb(materials, lesson_id: int):
    buttons = []
    for m in materials:
        label = m["caption"][:25] if m["caption"] else f"Файл #{m['id']}"
        buttons.append(
            [
                InlineKeyboardButton(f"✏️ {label}", callback_data=f"edit_material:{m['id']}:{lesson_id}"),
                InlineKeyboardButton("🗑", callback_data=f"delete_material:{m['id']}:{lesson_id}"),
            ]
        )
    buttons.append([InlineKeyboardButton("📎 Добавить файл", callback_data=f"add_material_existing:{lesson_id}")])
    buttons.append([InlineKeyboardButton("🔗 Добавить ссылку", callback_data=f"add_link_existing:{lesson_id}")])
    buttons.append([InlineKeyboardButton("⬅️ Назад", callback_data=f"manage_lesson:{lesson_id}")])
    return InlineKeyboardMarkup(buttons)


# ---------- Бонусные гайды ----------

def bonus_menu_kb():
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📎 Добавить файлом", callback_data="bonus_add")],
            [InlineKeyboardButton("🔗 Добавить ссылкой", callback_data="bonus_add_link")],
            [InlineKeyboardButton("📋 Список гайдов", callback_data="bonus_list")],
        ]
    )


def bonus_list_admin_kb(materials):
    buttons = []
    for m in materials:
        label = m["caption"][:25] if m["caption"] else f"Файл #{m['id']}"
        buttons.append(
            [
                InlineKeyboardButton(f"✏️ {label}", callback_data=f"edit_bonus:{m['id']}"),
                InlineKeyboardButton("🗑", callback_data=f"delete_bonus:{m['id']}"),
            ]
        )
    return InlineKeyboardMarkup(buttons)


def bonus_add_more_kb():
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("➕ Добавить ещё", callback_data="bonus_more")],
            [InlineKeyboardButton("✅ Готово", callback_data="bonus_add_done")],
        ]
    )


def edit_field_choice_kb(show_link_option: bool = False):
    buttons = [[InlineKeyboardButton("✏️ Изменить текст", callback_data="ef_text")]]
    if show_link_option:
        buttons.append([InlineKeyboardButton("📎 Заменить файлом", callback_data="ef_file")])
        buttons.append([InlineKeyboardButton("🔗 Заменить ссылкой", callback_data="ef_link")])
    else:
        buttons.append([InlineKeyboardButton("📎 Заменить файл", callback_data="ef_file")])
    return InlineKeyboardMarkup(buttons)


# ---------- Ученицы ----------

def students_list_kb(students):
    buttons = []
    for s in students:
        name = s["full_name"] or s["username"] or str(s["user_id"])
        buttons.append([InlineKeyboardButton(f"Ответы: {name}", callback_data=f"student_detail:{s['user_id']}")])
    return InlineKeyboardMarkup(buttons)
