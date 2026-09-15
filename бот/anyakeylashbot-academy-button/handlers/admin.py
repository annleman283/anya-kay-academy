import os

from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

import config
import database as db
import keyboards as kb
from config import ADMIN_IDS

# ---------- Состояния диалога "Добавить урок" ----------
(
    TITLE, DESCRIPTION, VIDEO_CHOICE, VIDEO_FILE, VIDEO_LINK,
    MATERIALS_MENU, MATERIAL_FILE, MATERIAL_LINK, MATERIAL_CAPTION,
    Q_TEXT, Q_PHOTO, Q_OPTIONS, Q_CORRECT, Q_EXPLANATION, Q_MENU,
) = range(15)

# ---------- Состояния диалога "Заменить видео" ----------
RV_CHOICE, RV_FILE, RV_LINK = range(100, 103)

# ---------- Состояния диалога "Название/описание" ----------
ET_TITLE, ET_DESC = range(200, 202)

# ---------- Состояния диалога "Добавить файл/ссылку к существующему уроку" ----------
EM_FILE, EM_LINK, EM_CAPTION = range(300, 303)

# ---------- Состояния диалога "Редактировать/добавить вопрос" ----------
QE_TEXT, QE_PHOTO, QE_OPTIONS, QE_CORRECT, QE_EXPLANATION = range(500, 505)

# ---------- Состояния диалога "Изменить текст/файл материала или гайда" ----------
EF_CHOICE, EF_TEXT, EF_FILE, EF_LINK = range(600, 604)

# ---------- Состояния диалога "Бонусный гайд" ----------
BONUS_MENU_CHOICE, BONUS_FILE, BONUS_LINK, BONUS_CAPTION = range(400, 404)


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


async def admin_only_guard(update: Update) -> bool:
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Эта функция доступна только администратору.")
        return False
    return True


async def admin_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывается администратору вместо обычного приветствия ученицы."""
    await update.message.reply_text(
        "Панель администратора школы. Пользуйтесь меню внизу экрана 👇\n\n"
        "🔄 «Проверить как ученица» сбросит ваш собственный тестовый прогресс и покажет курс "
        "точно так, как его видят ученицы — это не повлияет на реальную статистику.",
        reply_markup=kb.admin_menu(),
    )


# ==================== ДОБАВЛЕНИЕ УРОКА ====================

async def add_lesson_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await admin_only_guard(update):
        return ConversationHandler.END
    context.user_data["new_lesson"] = {}
    await update.message.reply_text(
        "Создаём новый урок.\n\nВведите название урока (например: «Урок 1. Материалы и инструменты»):\n\n"
        "Отменить в любой момент — /cancel"
    )
    return TITLE


async def add_lesson_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_lesson"]["title"] = update.message.text.strip()
    await update.message.reply_text(
        "Добавьте описание урока:", reply_markup=kb.skip_kb("skip_description")
    )
    return DESCRIPTION


async def add_lesson_description(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_lesson"]["description"] = update.message.text.strip()
    await update.message.reply_text("Как добавить видео этого урока?", reply_markup=kb.video_choice_kb())
    return VIDEO_CHOICE


async def add_lesson_description_skip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["new_lesson"]["description"] = ""
    await query.message.reply_text("Как добавить видео этого урока?", reply_markup=kb.video_choice_kb())
    return VIDEO_CHOICE


async def video_choice_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "vid_file":
        await query.message.reply_text("Отправьте видеофайл для этого урока (до 50 МБ):")
        return VIDEO_FILE
    else:
        await query.message.reply_text("Пришлите ссылку на видео (например, YouTube):")
        return VIDEO_LINK


async def _create_lesson_and_ask_materials(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = context.user_data["new_lesson"]
    lesson_id = db.add_lesson(
        data["title"], data.get("description", ""),
        data["video_type"], data.get("video_file_id"), data.get("video_url"),
    )
    context.user_data["new_lesson"]["id"] = lesson_id
    context.user_data["new_lesson"]["questions_added"] = 0
    await update.message.reply_text(
        "Видео сохранено ✅\n\nХотите прикрепить файл-пособие к этому уроку (PDF, презентация и т.п.)?",
        reply_markup=kb.materials_menu_kb(),
    )
    return MATERIALS_MENU


async def add_lesson_video_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    video = update.message.video or update.message.document
    if video is None:
        await update.message.reply_text("Пожалуйста, отправьте видеофайл.")
        return VIDEO_FILE
    context.user_data["new_lesson"]["video_type"] = "file"
    context.user_data["new_lesson"]["video_file_id"] = video.file_id
    context.user_data["new_lesson"]["video_url"] = None
    return await _create_lesson_and_ask_materials(update, context)


async def add_lesson_video_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    context.user_data["new_lesson"]["video_type"] = "link"
    context.user_data["new_lesson"]["video_file_id"] = None
    context.user_data["new_lesson"]["video_url"] = url
    return await _create_lesson_and_ask_materials(update, context)


async def materials_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "add_material":
        await query.message.reply_text("Пришлите файл (PDF, презентация, видео и т.п.):")
        return MATERIAL_FILE
    elif query.data == "add_material_link":
        await query.message.reply_text("Пришлите ссылку:")
        return MATERIAL_LINK
    else:
        await query.message.reply_text("Отправьте текст первого вопроса теста:")
        return Q_TEXT


async def add_material_link_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_lesson"]["current_material_file_id"] = update.message.text.strip()
    context.user_data["new_lesson"]["current_material_file_type"] = "link"
    await update.message.reply_text("Добавьте текст к этой ссылке — что это и для чего:")
    return MATERIAL_CAPTION


async def add_material_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    file_obj = update.message.document or update.message.video
    if file_obj is None:
        await update.message.reply_text("Пожалуйста, отправьте файл документом или видео.")
        return MATERIAL_FILE
    context.user_data["new_lesson"]["current_material_file_id"] = file_obj.file_id
    context.user_data["new_lesson"]["current_material_file_type"] = "video" if update.message.video else "document"
    await update.message.reply_text("Добавьте текст к этому файлу — что это и для чего:")
    return MATERIAL_CAPTION


async def add_material_caption(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = context.user_data["new_lesson"]
    db.add_lesson_material(
        data["id"], data.pop("current_material_file_id"), update.message.text.strip(),
        data.pop("current_material_file_type", "document"),
    )
    await update.message.reply_text("Файл добавлен ✅", reply_markup=kb.materials_menu_kb())
    return MATERIALS_MENU


async def add_question_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_lesson"]["current_q_text"] = update.message.text.strip()
    await update.message.reply_text(
        "Хотите прикрепить фото к этому вопросу? (например, показать фото работы и спросить, что не так)",
        reply_markup=kb.photo_choice_kb(),
    )
    return Q_PHOTO


async def question_photo_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "skip_q_photo":
        context.user_data["new_lesson"]["current_q_photo"] = None
        await query.message.reply_text(
            "Отправьте варианты ответов — каждый вариант с новой строки (минимум 2, максимум 6). Пример:\n\n"
            "Пинцет\nКлей\nВатные диски\nЛак для ногтей"
        )
        return Q_OPTIONS
    else:
        await query.message.reply_text("Пришлите фото к этому вопросу:")
        return Q_PHOTO


async def question_photo_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.photo:
        await update.message.reply_text("Пожалуйста, отправьте именно фото.")
        return Q_PHOTO
    context.user_data["new_lesson"]["current_q_photo"] = update.message.photo[-1].file_id
    await update.message.reply_text(
        "Фото добавлено ✅\n\nОтправьте варианты ответов — каждый вариант с новой строки "
        "(минимум 2, максимум 6):"
    )
    return Q_OPTIONS


async def add_question_options(update: Update, context: ContextTypes.DEFAULT_TYPE):
    options = [line.strip() for line in update.message.text.split("\n") if line.strip()]
    if len(options) < 2 or len(options) > 6:
        await update.message.reply_text("Нужно от 2 до 6 вариантов, каждый на новой строке. Отправьте ещё раз:")
        return Q_OPTIONS
    context.user_data["new_lesson"]["current_q_options"] = options
    numbered = "\n".join(f"{i + 1}. {opt}" for i, opt in enumerate(options))
    await update.message.reply_text(
        f"Варианты:\n{numbered}\n\nКакой из них правильный? Нажмите на нужную кнопку:",
        reply_markup=kb.correct_option_kb(options),
    )
    return Q_CORRECT


async def add_question_correct(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    correct_index = int(query.data.split(":")[1])
    context.user_data["new_lesson"]["current_q_correct"] = correct_index
    await query.message.reply_text(
        "Добавьте короткое пояснение, почему это правильный ответ (покажется ученице после теста):",
        reply_markup=kb.skip_kb("skip_explanation"),
    )
    return Q_EXPLANATION


async def _save_current_question(context: ContextTypes.DEFAULT_TYPE, explanation: str):
    data = context.user_data["new_lesson"]
    db.add_question(
        data["id"], data["current_q_text"], data["current_q_options"],
        data["current_q_correct"], explanation, data.get("current_q_photo"),
    )
    data["questions_added"] += 1


async def add_question_explanation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _save_current_question(context, update.message.text.strip())
    await update.message.reply_text(
        f"Вопрос добавлен ✅ (всего вопросов: {context.user_data['new_lesson']['questions_added']})",
        reply_markup=kb.question_menu_kb(),
    )
    return Q_MENU


async def add_question_explanation_skip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await _save_current_question(context, "")
    await query.message.reply_text(
        f"Вопрос добавлен ✅ (всего вопросов: {context.user_data['new_lesson']['questions_added']})",
        reply_markup=kb.question_menu_kb(),
    )
    return Q_MENU


async def question_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "more_question":
        await query.message.reply_text("Отправьте текст следующего вопроса:")
        return Q_TEXT
    else:
        data = context.user_data.pop("new_lesson", {})
        await query.message.reply_text(
            f"Урок «{data.get('title', '')}» сохранён с {data.get('questions_added', 0)} вопросами. "
            "Готово! ✅",
            reply_markup=kb.admin_menu(),
        )
        return ConversationHandler.END


async def add_lesson_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = context.user_data.get("new_lesson")
    if data and (data.get("id") or data.get("title")):
        await update.message.reply_text(
            "Вы уже начали заполнять этот урок — точно отменить и удалить всё, что успели ввести?",
            reply_markup=kb.confirm_kb("confirm_cancel_lesson", "keep_editing_lesson"),
        )
        return None
    context.user_data.pop("new_lesson", None)
    await update.message.reply_text("Создание урока отменено.", reply_markup=kb.admin_menu())
    return ConversationHandler.END


async def confirm_cancel_lesson_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = context.user_data.pop("new_lesson", None)
    if data and data.get("id"):
        db.delete_lesson(data["id"])
    await query.message.reply_text("Урок удалён, создание отменено.", reply_markup=kb.admin_menu())
    return ConversationHandler.END


async def keep_editing_lesson_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text("Хорошо, продолжайте с того же места, где остановились 🙂")


async def generic_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("edit_lesson_id", None)
    context.user_data.pop("edit_new_title", None)
    context.user_data.pop("existing_material_file_id", None)
    context.user_data.pop("bonus_file_id", None)
    await update.message.reply_text("Отменено.", reply_markup=kb.admin_menu())
    return ConversationHandler.END


# ==================== СПИСОК И УПРАВЛЕНИЕ УРОКАМИ ====================

async def list_lessons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await admin_only_guard(update):
        return
    lessons = db.get_all_lessons()
    if not lessons:
        await update.message.reply_text("Уроков пока нет. Нажмите «➕ Добавить урок».")
        return
    await update.message.reply_text("📚 Выберите урок для управления:", reply_markup=kb.lessons_list_admin_kb(lessons))


async def manage_lesson_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lesson_id = int(query.data.split(":")[1])
    lesson = db.get_lesson_by_id(lesson_id)
    if lesson is None:
        await query.message.reply_text("Урок не найден (возможно, уже удалён).")
        return
    await query.message.reply_text(
        lesson["title"],
        reply_markup=kb.manage_lesson_kb(lesson_id),
    )


async def back_to_lessons_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lessons = db.get_all_lessons()
    await query.message.reply_text("📚 Выберите урок для управления:", reply_markup=kb.lessons_list_admin_kb(lessons))


async def preview_lesson_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lesson_id = int(query.data.split(":")[1])
    from handlers.student import _send_lesson_video_and_materials
    lesson = db.get_lesson_by_id(lesson_id)
    if lesson is None:
        return
    await query.message.reply_text("👁 Вот что увидит ученица (предпросмотр):")
    await _send_lesson_video_and_materials(query.message.chat_id, lesson, context)


# ---------- Удаление урока (с подтверждением) ----------

async def delete_lesson_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lesson_id = int(query.data.split(":")[1])
    lesson = db.get_lesson_by_id(lesson_id)
    if lesson is None:
        return
    await query.message.reply_text(
        f"Точно удалить урок «{lesson['title']}»? Это необратимо, вопросы и файлы тоже удалятся.",
        reply_markup=kb.confirm_kb(f"confirm_delete_lesson:{lesson_id}", "cancel_delete"),
    )


async def confirm_delete_lesson_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lesson_id = int(query.data.split(":")[1])
    db.delete_lesson(lesson_id)
    await query.message.reply_text("Урок удалён ✅", reply_markup=kb.admin_menu())


async def cancel_delete_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text("Отменено.")


# ---------- Заменить видео ----------

async def replace_video_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lesson_id = int(query.data.split(":")[1])
    context.user_data["edit_lesson_id"] = lesson_id
    await query.message.reply_text("Как добавить новое видео?", reply_markup=kb.video_choice_kb())
    return RV_CHOICE


async def replace_video_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "vid_file":
        await query.message.reply_text("Отправьте новый видеофайл:")
        return RV_FILE
    else:
        await query.message.reply_text("Пришлите новую ссылку на видео:")
        return RV_LINK


async def replace_video_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    video = update.message.video or update.message.document
    if video is None:
        await update.message.reply_text("Пожалуйста, отправьте видеофайл.")
        return RV_FILE
    lesson_id = context.user_data.pop("edit_lesson_id")
    db.update_lesson_video(lesson_id, "file", video.file_id, None)
    await update.message.reply_text("Видео заменено ✅", reply_markup=kb.admin_menu())
    return ConversationHandler.END


async def replace_video_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lesson_id = context.user_data.pop("edit_lesson_id")
    db.update_lesson_video(lesson_id, "link", None, update.message.text.strip())
    await update.message.reply_text("Видео заменено ✅", reply_markup=kb.admin_menu())
    return ConversationHandler.END


# ---------- Изменить название/описание ----------

async def edit_title_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lesson_id = int(query.data.split(":")[1])
    context.user_data["edit_lesson_id"] = lesson_id
    await query.message.reply_text("Отправьте новое название урока:")
    return ET_TITLE


async def edit_title_save(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["edit_new_title"] = update.message.text.strip()
    await update.message.reply_text(
        "Отправьте новое описание:", reply_markup=kb.skip_kb("skip_edit_description")
    )
    return ET_DESC


async def _finish_edit_title(update_or_query, context: ContextTypes.DEFAULT_TYPE, description: str):
    lesson_id = context.user_data.pop("edit_lesson_id")
    title = context.user_data.pop("edit_new_title")
    db.update_lesson_text(lesson_id, title, description)
    await update_or_query.reply_text("Название и описание обновлены ✅", reply_markup=kb.admin_menu())
    return ConversationHandler.END


async def edit_desc_save(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await _finish_edit_title(update.message, context, update.message.text.strip())


async def edit_desc_skip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    return await _finish_edit_title(query.message, context, "")


# ---------- Управление файлами существующего урока ----------

async def manage_materials_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lesson_id = int(query.data.split(":")[1])
    materials = db.get_materials_for_lesson(lesson_id)
    text = "📎 Файлы этого урока:" if materials else "У этого урока пока нет файлов."
    await query.message.reply_text(text, reply_markup=kb.materials_manage_kb(materials, lesson_id))


async def delete_material_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, material_id_str, lesson_id_str = query.data.split(":")
    db.delete_lesson_material(int(material_id_str))
    materials = db.get_materials_for_lesson(int(lesson_id_str))
    await query.message.reply_text("Файл удалён ✅", reply_markup=kb.materials_manage_kb(materials, int(lesson_id_str)))


async def add_material_existing_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lesson_id = int(query.data.split(":")[1])
    context.user_data["edit_lesson_id"] = lesson_id
    await query.message.reply_text("Пришлите файл (документ или видео):")
    return EM_FILE


async def add_link_existing_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lesson_id = int(query.data.split(":")[1])
    context.user_data["edit_lesson_id"] = lesson_id
    await query.message.reply_text("Пришлите ссылку:")
    return EM_LINK


async def add_link_existing_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["existing_material_file_id"] = update.message.text.strip()
    context.user_data["existing_material_file_type"] = "link"
    await update.message.reply_text("Добавьте текст к этой ссылке:")
    return EM_CAPTION


async def add_material_existing_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    file_obj = update.message.document or update.message.video
    if file_obj is None:
        await update.message.reply_text("Пожалуйста, отправьте файл документом или видео.")
        return EM_FILE
    context.user_data["existing_material_file_id"] = file_obj.file_id
    context.user_data["existing_material_file_type"] = "video" if update.message.video else "document"
    await update.message.reply_text("Добавьте текст к этому файлу:")
    return EM_CAPTION


async def add_material_existing_caption(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lesson_id = context.user_data.pop("edit_lesson_id")
    file_id = context.user_data.pop("existing_material_file_id")
    file_type = context.user_data.pop("existing_material_file_type", "document")
    db.add_lesson_material(lesson_id, file_id, update.message.text.strip(), file_type)
    await update.message.reply_text("Файл добавлен ✅", reply_markup=kb.admin_menu())
    return ConversationHandler.END


# ==================== БОНУСНЫЕ ГАЙДЫ ====================

async def bonus_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await admin_only_guard(update):
        return
    await update.message.reply_text("🎁 Бонусные гайды курса:", reply_markup=kb.bonus_menu_kb())


async def bonus_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "bonus_list":
        materials = db.get_all_bonus_materials()
        text = "Список бонусных гайдов:" if materials else "Гайдов пока нет."
        await query.message.reply_text(text, reply_markup=kb.bonus_list_admin_kb(materials))
        return ConversationHandler.END
    elif query.data == "bonus_add_link":
        await query.message.reply_text("Пришлите ссылку:")
        return BONUS_LINK
    else:
        await query.message.reply_text("Пришлите файл гайда (документ или видео):")
        return BONUS_FILE


async def bonus_add_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    file_obj = update.message.document or update.message.video
    if file_obj is None:
        await update.message.reply_text("Пожалуйста, отправьте файл документом или видео.")
        return BONUS_FILE
    context.user_data["bonus_file_id"] = file_obj.file_id
    context.user_data["bonus_file_type"] = "video" if update.message.video else "document"
    await update.message.reply_text("Добавьте текст-описание к этому гайду:")
    return BONUS_CAPTION


async def bonus_add_link_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["bonus_file_id"] = update.message.text.strip()
    context.user_data["bonus_file_type"] = "link"
    await update.message.reply_text("Добавьте текст-описание к этой ссылке:")
    return BONUS_CAPTION


async def bonus_add_caption(update: Update, context: ContextTypes.DEFAULT_TYPE):
    file_id = context.user_data.pop("bonus_file_id")
    file_type = context.user_data.pop("bonus_file_type", "document")
    db.add_bonus_material(file_id, update.message.text.strip(), file_type)
    await update.message.reply_text("Гайд добавлен ✅", reply_markup=kb.bonus_add_more_kb())
    return ConversationHandler.END


async def bonus_add_more_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "bonus_more":
        await query.message.reply_text("Как добавить следующий гайд?", reply_markup=kb.bonus_menu_kb())
        return BONUS_MENU_CHOICE
    else:
        await query.message.reply_text("Готово ✅", reply_markup=kb.admin_menu())
        return ConversationHandler.END


async def delete_bonus_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    material_id = int(query.data.split(":")[1])
    db.delete_bonus_material(material_id)
    materials = db.get_all_bonus_materials()
    text = "Гайд удалён ✅\n\nОставшиеся гайды:" if materials else "Гайд удалён ✅\n\nБольше гайдов нет."
    await query.message.reply_text(text, reply_markup=kb.bonus_list_admin_kb(materials))


# ==================== УЧЕНИЦЫ ====================

async def list_students(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await admin_only_guard(update):
        return
    students = db.get_all_students()
    if not students:
        await update.message.reply_text("Пока никто не начал обучение.")
        return

    max_order = db.get_max_lesson_order()
    lines = ["👩‍🎓 Ученицы:\n"]
    for s in students:
        name = s["full_name"] or s["username"] or str(s["user_id"])
        uname = f"@{s['username']}" if s["username"] else ""
        lines.append(f"• {name} {uname} — урок {min(s['current_lesson_order'], max_order)}/{max_order}")
    await update.message.reply_text("\n".join(lines), reply_markup=kb.students_list_kb(students))


async def student_detail_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not is_admin(update.effective_user.id):
        await query.answer("Только для администратора", show_alert=True)
        return
    await query.answer()

    user_id = int(query.data.split(":")[1])
    student = db.get_student(user_id)
    attempts = db.get_attempts_for_student(user_id)

    if not attempts:
        await query.message.reply_text("У этой ученицы пока нет пройденных тестов.")
        return

    name = student["full_name"] or student["username"] or str(user_id)
    report_lines = [f"📋 Ответы ученицы: {name}\n"]

    for att in attempts:
        lesson = db.get_lesson_by_id(att["lesson_id"])
        status = "✅ пройден" if att["passed"] else "❌ не пройден"
        report_lines.append(
            f"\n{lesson['title']} "
            f"— попытка {att['attempt_number']}, {att['score']}/{att['total']} {status}"
        )
        answers = db.get_answers_for_attempt(att["id"])
        for a in answers:
            mark = "✅" if a["is_correct"] else "❌"
            line = f"   {mark} «{a['question_text']}» → ответ: {a['chosen_text']}"
            if not a["is_correct"]:
                line += f" (правильно: {a['correct_text']})"
            report_lines.append(line)

    text = "\n".join(report_lines)
    for i in range(0, len(text), 3500):
        await query.message.reply_text(text[i:i + 3500])


# ==================== СЛУЖЕБНОЕ: РЕЗЕРВНАЯ КОПИЯ, ТЕСТ-РЕЖИМ ====================

async def backup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await admin_only_guard(update):
        return
    if not os.path.exists(config.DB_PATH):
        await update.message.reply_text("Файл базы данных не найден.")
        return
    await update.message.reply_document(
        document=open(config.DB_PATH, "rb"),
        filename="lessons_backup.db",
        caption="Резервная копия базы данных бота 💾",
    )


async def test_mode_reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await admin_only_guard(update):
        return
    user = update.effective_user
    db.ensure_student(user.id, user.username or "", user.full_name or "")
    db.reset_student_progress(user.id)
    await update.message.reply_text(
        "Ваш тестовый прогресс сброшен. Сейчас увидите курс точно так, как его видит ученица "
        "(это не повлияет на реальную статистику).",
        reply_markup=kb.student_menu(),
    )
    from handlers.student import begin_learning_callback, send_lesson
    await send_lesson(update.effective_chat.id, 1, context)


# ==================== ВОПРОСЫ СУЩЕСТВУЮЩЕГО УРОКА ====================

async def manage_questions_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lesson_id = int(query.data.split(":")[1])
    questions = db.get_questions_for_lesson(lesson_id)
    text = "❓ Вопросы этого урока:" if questions else "У этого урока пока нет вопросов."
    await query.message.reply_text(text, reply_markup=kb.questions_manage_kb(questions, lesson_id))


async def delete_question_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, question_id_str, lesson_id_str = query.data.split(":")
    await query.message.reply_text(
        "Точно удалить этот вопрос?",
        reply_markup=kb.confirm_kb(f"confirm_delete_question:{question_id_str}:{lesson_id_str}", "cancel_delete"),
    )


async def confirm_delete_question_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, question_id_str, lesson_id_str = query.data.split(":")
    db.delete_question(int(question_id_str))
    questions = db.get_questions_for_lesson(int(lesson_id_str))
    text = "Вопрос удалён ✅\n\nОставшиеся вопросы:" if questions else "Вопрос удалён ✅\n\nБольше вопросов нет."
    await query.message.reply_text(text, reply_markup=kb.questions_manage_kb(questions, int(lesson_id_str)))


async def qedit_add_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lesson_id = int(query.data.split(":")[1])
    context.user_data["qedit"] = {"mode": "add", "lesson_id": lesson_id}
    await query.message.reply_text("Отправьте текст нового вопроса:")
    return QE_TEXT


async def qedit_edit_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    question_id = int(query.data.split(":")[1])
    q = db.get_question_by_id(question_id)
    if q is None:
        await query.message.reply_text("Вопрос не найден (возможно, уже удалён).")
        return ConversationHandler.END
    context.user_data["qedit"] = {"mode": "edit", "question_id": question_id, "lesson_id": q["lesson_id"]}
    await query.message.reply_text(
        f"Текущий текст вопроса:\n«{q['question_text']}»\n\nОтправьте новый текст вопроса (полностью заменит старый):"
    )
    return QE_TEXT


async def qedit_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["qedit"]["text"] = update.message.text.strip()
    await update.message.reply_text(
        "Хотите прикрепить (или заменить) фото к этому вопросу?", reply_markup=kb.photo_choice_kb()
    )
    return QE_PHOTO


async def qedit_photo_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "skip_q_photo":
        context.user_data["qedit"]["photo"] = None
        await query.message.reply_text(
            "Отправьте варианты ответов — каждый вариант с новой строки (минимум 2, максимум 6):"
        )
        return QE_OPTIONS
    else:
        await query.message.reply_text("Пришлите фото:")
        return QE_PHOTO


async def qedit_photo_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.photo:
        await update.message.reply_text("Пожалуйста, отправьте именно фото.")
        return QE_PHOTO
    context.user_data["qedit"]["photo"] = update.message.photo[-1].file_id
    await update.message.reply_text(
        "Фото сохранено ✅\n\nОтправьте варианты ответов — каждый вариант с новой строки "
        "(минимум 2, максимум 6):"
    )
    return QE_OPTIONS


async def qedit_options(update: Update, context: ContextTypes.DEFAULT_TYPE):
    options = [line.strip() for line in update.message.text.split("\n") if line.strip()]
    if len(options) < 2 or len(options) > 6:
        await update.message.reply_text("Нужно от 2 до 6 вариантов, каждый на новой строке. Отправьте ещё раз:")
        return QE_OPTIONS
    context.user_data["qedit"]["options"] = options
    numbered = "\n".join(f"{i + 1}. {opt}" for i, opt in enumerate(options))
    await update.message.reply_text(
        f"Варианты:\n{numbered}\n\nКакой из них правильный?", reply_markup=kb.correct_option_kb(options)
    )
    return QE_CORRECT


async def qedit_correct(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    idx = int(query.data.split(":")[1])
    context.user_data["qedit"]["correct"] = idx
    await query.message.reply_text(
        "Добавьте пояснение к ответу:", reply_markup=kb.skip_kb("skip_qedit_explanation")
    )
    return QE_EXPLANATION


def _save_qedit(context: ContextTypes.DEFAULT_TYPE, explanation: str):
    d = context.user_data.pop("qedit")
    if d["mode"] == "add":
        db.add_question(d["lesson_id"], d["text"], d["options"], d["correct"], explanation, d.get("photo"))
    else:
        db.update_question(d["question_id"], d["text"], d["options"], d["correct"], explanation, d.get("photo"))


async def qedit_explanation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _save_qedit(context, update.message.text.strip())
    await update.message.reply_text("Вопрос сохранён ✅", reply_markup=kb.admin_menu())
    return ConversationHandler.END


async def qedit_explanation_skip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _save_qedit(context, "")
    await query.message.reply_text("Вопрос сохранён ✅", reply_markup=kb.admin_menu())
    return ConversationHandler.END


# ==================== РЕДАКТИРОВАНИЕ ФАЙЛОВ И ГАЙДОВ ====================

async def edit_material_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, material_id_str, lesson_id_str = query.data.split(":")
    context.user_data["ef"] = {"kind": "material", "id": int(material_id_str), "lesson_id": int(lesson_id_str)}
    await query.message.reply_text(
        "Что хотите изменить у этого файла?", reply_markup=kb.edit_field_choice_kb(show_link_option=True)
    )
    return EF_CHOICE


async def edit_bonus_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    material_id = int(query.data.split(":")[1])
    context.user_data["ef"] = {"kind": "bonus", "id": material_id}
    await query.message.reply_text(
        "Что хотите изменить у этого гайда?", reply_markup=kb.edit_field_choice_kb(show_link_option=True)
    )
    return EF_CHOICE


async def edit_field_choice_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "ef_text":
        await query.message.reply_text("Отправьте новый текст-описание:")
        return EF_TEXT
    elif query.data == "ef_link":
        await query.message.reply_text("Пришлите новую ссылку:")
        return EF_LINK
    else:
        await query.message.reply_text("Пришлите новый файл (документ или видео):")
        return EF_FILE


async def edit_field_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ef = context.user_data.pop("ef")
    url = update.message.text.strip()
    if ef["kind"] == "material":
        db.update_lesson_material_file(ef["id"], url, "link")
    else:
        db.update_bonus_material_file(ef["id"], url, "link")
    await update.message.reply_text("Ссылка обновлена ✅", reply_markup=kb.admin_menu())
    return ConversationHandler.END


async def edit_field_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ef = context.user_data.pop("ef")
    caption = update.message.text.strip()
    if ef["kind"] == "material":
        db.update_lesson_material_caption(ef["id"], caption)
    else:
        db.update_bonus_material_caption(ef["id"], caption)
    await update.message.reply_text("Текст обновлён ✅", reply_markup=kb.admin_menu())
    return ConversationHandler.END


async def edit_field_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    file_obj = update.message.document or update.message.video
    if file_obj is None:
        await update.message.reply_text("Пожалуйста, отправьте файл документом или видео.")
        return EF_FILE
    ef = context.user_data.pop("ef")
    if ef["kind"] == "material":
        file_type = "video" if update.message.video else "document"
        db.update_lesson_material_file(ef["id"], file_obj.file_id, file_type)
    else:
        db.update_bonus_material_file(ef["id"], file_obj.file_id)
    await update.message.reply_text("Файл обновлён ✅", reply_markup=kb.admin_menu())
    return ConversationHandler.END
