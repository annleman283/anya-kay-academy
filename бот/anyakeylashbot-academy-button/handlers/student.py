import asyncio
import random

from telegram import Update
from telegram.ext import ContextTypes

import config
import database as db
import keyboards as kb

SCHOOL_NAME = "Ани Кей"

WELCOME_MSG_1 = (
    "Привет, {first_name}! 👋\n"
    f"Это учебный бот школы {SCHOOL_NAME} по базовому курсу наращивания ресниц — теоретическая часть.\n\n"
    "Как это устроено:\n"
    "1️⃣ Смотрите видео-урок\n"
    "2️⃣ Проходите тест по нему\n"
    "3️⃣ Если все ответы верны — открывается следующий урок\n\n"
    "Количество попыток прохождения теста не ограничено — пересматривайте видео и пробуйте снова, "
    "сколько потребуется. Главное — ответить правильно на все вопросы."
)

WELCOME_MSG_2 = (
    "⚠️ Важно!\n"
    "Всю теорию и все тесты нужно пройти полностью до начала очного практического курса. "
    "Без этого вы не будете допущены к работе с живыми моделями.\n"
    "Пожалуйста, рассчитайте своё время заранее 🙏"
)

WELCOME_MSG_3 = (
    "Готовы начать?\n\n"
    "Кнопка «📊 Мой прогресс» — это ваш личный список уроков: что уже пройдено ✅, что доступно "
    "сейчас ▶️ и что ещё впереди 🔒. Внизу экрана теперь есть постоянное меню — им можно "
    "пользоваться в любой момент."
)

WELCOME_BACK_MSG = "С возвращением, {first_name}! 👋"

REMINDER_MSG = (
    "Привет, {first_name}! 👋\n"
    "Давно не виделись — вы не заходили в бот больше {days} дней.\n\n"
    "Не забывайте: всю теорию нужно пройти до начала практического курса, иначе не будет допуска "
    "к работе с моделями. Самое время вернуться к обучению 💪"
)

FINAL_CONGRATS_MSG = (
    "🥰 {first_name}, вы просто умница!\n\n"
    "Вся теория позади, все тесты сданы — вы старались, разбирались, не сдавались. Это правда "
    "большая работа, и я вижу, как вы выросли за это время 💛\n\n"
    "Совсем скоро увидимся на практике, где ваши ручки наконец возьмут пинцет вживую 🦋 "
    "Обнимаю и жду встречи!\n\n"
    "Загляните в «🎁 Мои гайды» — там для вас подарок."
)

HELP_TEXT = (
    "ℹ️ Как пользоваться ботом\n\n"
    "📚 Все уроки — список уроков, можно сразу перейти к любому пройденному или текущему\n"
    "📊 Мой прогресс — сколько уроков пройдено, что осталось\n"
    "🎁 Мои гайды — бонусные материалы (откроются после прохождения всей теории)\n\n"
    "Чтобы двигаться дальше по урокам, нужно правильно ответить на все вопросы теста — но "
    "попыток неограниченное количество, пересматривайте видео и пробуйте снова 💛"
)

FALLBACK_MSG = "Пожалуйста, воспользуйтесь кнопками ниже 👇"


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    is_new = db.ensure_student(user.id, user.username or "", user.full_name or "")
    db.touch_activity(user.id)
    chat_id = update.effective_chat.id

    if not is_new:
        await update.message.reply_text(
            WELCOME_BACK_MSG.format(first_name=user.first_name),
            reply_markup=kb.student_menu(),
        )
        return

    await update.message.reply_text(WELCOME_MSG_1.format(first_name=user.first_name))
    await context.bot.send_chat_action(chat_id, "typing")
    await asyncio.sleep(1)

    await context.bot.send_message(chat_id, WELCOME_MSG_2)
    await context.bot.send_chat_action(chat_id, "typing")
    await asyncio.sleep(1)

    await context.bot.send_message(chat_id, WELCOME_MSG_3, reply_markup=kb.student_menu())
    await context.bot.send_message(chat_id, "Готовы начать?", reply_markup=kb.welcome_kb())


async def begin_learning_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    db.touch_activity(user_id)
    student = db.get_student(user_id)
    await send_lesson(query.message.chat_id, student["current_lesson_order"], context)


async def _send_lesson_video_and_materials(chat_id: int, lesson, context: ContextTypes.DEFAULT_TYPE):
    caption = f"📚 {lesson['title']}"
    if lesson["description"]:
        caption += f"\n\n{lesson['description']}"

    if lesson["video_type"] == "link" and lesson["video_url"]:
        await context.bot.send_message(chat_id, f"{caption}\n\n🎥 Видео урока:\n{lesson['video_url']}")
    elif lesson["video_file_id"]:
        await context.bot.send_video(chat_id, lesson["video_file_id"], caption=caption)
    else:
        await context.bot.send_message(chat_id, caption)

    for m in db.get_materials_for_lesson(lesson["id"]):
        if m["file_type"] == "video":
            await context.bot.send_video(chat_id, m["file_id"], caption=m["caption"] or None)
        elif m["file_type"] == "link":
            text = f"🔗 {m['caption']}\n{m['file_id']}" if m["caption"] else m["file_id"]
            await context.bot.send_message(chat_id, text)
        else:
            await context.bot.send_document(chat_id, m["file_id"], caption=m["caption"] or None)


async def send_lesson(chat_id: int, order_num: int, context: ContextTypes.DEFAULT_TYPE):
    lesson = db.get_lesson_by_order(order_num)
    if lesson is None:
        max_order = db.get_max_lesson_order()
        if not (order_num > max_order and max_order > 0):
            await context.bot.send_message(chat_id, "Пока нет доступных уроков. Загляните позже 🙂")
        return

    await _send_lesson_video_and_materials(chat_id, lesson, context)

    questions = db.get_questions_for_lesson(lesson["id"])
    if questions:
        await context.bot.send_message(
            chat_id,
            "Когда посмотрите урок — нажмите кнопку ниже, чтобы пройти тест.",
            reply_markup=kb.lesson_kb(lesson["id"]),
        )
    else:
        db.unlock_next_lesson(chat_id, lesson["order_num"])
        await context.bot.send_message(
            chat_id,
            "Для этого урока нет теста — переходим дальше 👇",
            reply_markup=kb.next_lesson_kb(),
        )


async def rewatch_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lesson_id = int(query.data.split(":")[1])
    lesson = db.get_lesson_by_id(lesson_id)
    if lesson is None:
        return
    await _send_lesson_video_and_materials(query.message.chat_id, lesson, context)
    await context.bot.send_message(
        query.message.chat_id,
        "Когда пересмотрите — можно пробовать тест снова.",
        reply_markup=kb.lesson_kb(lesson_id),
    )


# ---------- Постоянное меню: "Все уроки" ----------

async def all_lessons_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    db.ensure_student(user_id, update.effective_user.username or "", update.effective_user.full_name or "")
    db.touch_activity(user_id)
    student = db.get_student(user_id)
    lessons = db.get_all_lessons()
    if not lessons:
        await update.message.reply_text("Уроков пока нет.")
        return
    await update.message.reply_text(
        "📚 Выберите урок:",
        reply_markup=kb.all_lessons_kb(lessons, student["current_lesson_order"]),
    )


async def open_lesson_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    order_num = int(query.data.split(":")[1])
    user_id = update.effective_user.id
    student = db.get_student(user_id)
    if order_num > student["current_lesson_order"]:
        await query.answer("Этот урок пока закрыт — сначала пройдите предыдущие 🔒", show_alert=True)
        return
    await query.answer()
    await send_lesson(query.message.chat_id, order_num, context)


# ---------- Постоянное меню: "Мой прогресс" ----------

async def progress_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _send_progress(update.effective_user.id, update.effective_chat.id, context)


async def show_progress_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await _send_progress(update.effective_user.id, query.message.chat_id, context)


async def _send_progress(user_id: int, chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    student = db.get_student(user_id)
    if student is None:
        await context.bot.send_message(chat_id, "Нажмите /start, чтобы начать обучение.")
        return

    lessons = db.get_all_lessons()
    if not lessons:
        await context.bot.send_message(chat_id, "Уроков пока нет.")
        return

    current = student["current_lesson_order"]
    done = min(current - 1, len(lessons))
    lines = [f"📊 Ваш прогресс: {done} из {len(lessons)} уроков пройдено\n"]
    for l in lessons:
        if l["order_num"] < current:
            icon = "✅"
        elif l["order_num"] == current:
            icon = "▶️"
        else:
            icon = "🔒"
        suffix = "  ← вы здесь" if l["order_num"] == current else ""
        lines.append(f"{icon} {l['title']}{suffix}")

    await context.bot.send_message(chat_id, "\n".join(lines))


# ---------- Постоянное меню: "Мои гайды" ----------

async def guides_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    student = db.get_student(user_id)
    max_order = db.get_max_lesson_order()
    if student is None or student["current_lesson_order"] <= max_order or max_order == 0:
        await update.message.reply_text(
            "Гайды откроются после прохождения всей теории 💛 Осталось совсем немного!"
        )
        return

    bonuses = db.get_all_bonus_materials()
    if not bonuses:
        await update.message.reply_text("Пока здесь пусто — загляните позже 🎁")
        return

    await update.message.reply_text("Вот ваши бонусные гайды к курсу 🎁")
    for m in bonuses:
        if m["file_type"] == "video":
            await update.message.reply_video(m["file_id"], caption=m["caption"] or None)
        elif m["file_type"] == "link":
            text = f"🔗 {m['caption']}\n{m['file_id']}" if m["caption"] else m["file_id"]
            await update.message.reply_text(text)
        else:
            await update.message.reply_document(m["file_id"], caption=m["caption"] or None)


# ---------- Постоянное меню: "Помощь" ----------

async def help_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HELP_TEXT)


# ---------- Заглушка на непонятные сообщения ----------

async def fallback_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message is None:
        return
    await update.message.reply_text(FALLBACK_MSG, reply_markup=kb.student_menu())


# ---------- Тест ----------

def _shuffled_questions(questions: list) -> list:
    shuffled = []
    for q in questions:
        q_copy = dict(q)
        correct_text = q["options"][q["correct_index"]]
        new_options = q["options"][:]
        random.shuffle(new_options)
        q_copy["options"] = new_options
        q_copy["correct_index"] = new_options.index(correct_text)
        shuffled.append(q_copy)
    random.shuffle(shuffled)
    return shuffled


def _init_quiz_state(context: ContextTypes.DEFAULT_TYPE, lesson_id: int, questions: list, attempt_number: int):
    context.user_data["quiz"] = {
        "lesson_id": lesson_id,
        "questions": questions,
        "idx": 0,
        "answers": [],
        "attempt_number": attempt_number,
    }


async def _ask_current_question(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    state = context.user_data["quiz"]
    q = state["questions"][state["idx"]]
    n = state["idx"] + 1
    total = len(state["questions"])
    options_text = "\n".join(f"{i + 1}. {opt}" for i, opt in enumerate(q["options"]))
    caption = f"❓ Вопрос {n} из {total}:\n\n{q['question_text']}\n\n{options_text}"
    markup = kb.question_kb(state["lesson_id"], q["id"], q["options"])
    if q.get("photo_file_id"):
        await context.bot.send_photo(chat_id, q["photo_file_id"], caption=caption, reply_markup=markup)
    else:
        await context.bot.send_message(chat_id, caption, reply_markup=markup)


async def start_quiz_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lesson_id = int(query.data.split(":")[1])
    questions = db.get_questions_for_lesson(lesson_id)
    if not questions:
        await query.message.reply_text("Для этого урока нет теста.")
        return

    user_id = update.effective_user.id
    db.touch_activity(user_id)
    attempt_number = db.next_attempt_number(user_id, lesson_id)
    questions = _shuffled_questions(questions)
    _init_quiz_state(context, lesson_id, questions, attempt_number)
    await _ask_current_question(query.message.chat_id, context)


async def answer_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    state = context.user_data.get("quiz")
    if state is None:
        await query.message.reply_text("Сессия теста устарела. Откройте урок заново через «📚 Все уроки».")
        return

    _, lesson_id_str, question_id_str, chosen_idx_str = query.data.split(":")
    lesson_id = int(lesson_id_str)
    question_id = int(question_id_str)
    chosen_idx = int(chosen_idx_str)

    current_q = state["questions"][state["idx"]]
    if current_q["id"] != question_id or state["lesson_id"] != lesson_id:
        return

    is_correct = chosen_idx == current_q["correct_index"]
    chosen_text = current_q["options"][chosen_idx]
    correct_text = current_q["options"][current_q["correct_index"]]
    state["answers"].append(
        {
            "question_id": question_id,
            "question_text": current_q["question_text"],
            "chosen_text": chosen_text,
            "correct_text": correct_text,
            "is_correct": is_correct,
        }
    )

    if is_correct:
        mark = "✅ Верно!"
    else:
        mark = f"❌ Неверно. Правильный ответ: {correct_text}"
    if current_q.get("explanation"):
        mark += f"\n\n💡 {current_q['explanation']}"

    result_text = f"{current_q['question_text']}\n\n{mark}"
    if query.message.photo:
        await query.edit_message_caption(caption=result_text)
    else:
        await query.edit_message_text(result_text)

    state["idx"] += 1
    if state["idx"] < len(state["questions"]):
        await _ask_current_question(query.message.chat_id, context)
    else:
        await _finish_quiz(update.effective_user.id, query.message.chat_id, context)


async def _finish_quiz(user_id: int, chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    state = context.user_data.pop("quiz")
    total = len(state["answers"])
    score = sum(1 for a in state["answers"] if a["is_correct"])
    lesson = db.get_lesson_by_id(state["lesson_id"])

    passed = (score / total) >= config.PASS_THRESHOLD if total else False

    db.save_attempt(
        user_id, state["lesson_id"], state["attempt_number"], state["answers"], score, total, passed
    )

    if not passed:
        await context.bot.send_message(
            chat_id,
            f"Результат теста: {score} из {total}.\n"
            "Для перехода к следующему уроку нужно ответить правильно на все вопросы. "
            "Пересмотрите видео и попробуйте ещё раз 💪",
            reply_markup=kb.retry_kb(state["lesson_id"]),
        )
        return

    db.unlock_next_lesson(user_id, lesson["order_num"])
    max_order = db.get_max_lesson_order()

    if lesson["order_num"] >= max_order:
        user = await context.bot.get_chat(user_id)
        await context.bot.send_message(chat_id, FINAL_CONGRATS_MSG.format(first_name=user.first_name))
    else:
        await context.bot.send_message(
            chat_id,
            f"🎉 Тест пройден! Правильных ответов: {score} из {total}.\nСледующий урок открыт!",
            reply_markup=kb.next_lesson_kb(),
        )


async def next_lesson_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    db.touch_activity(user_id)
    student = db.get_student(user_id)
    await send_lesson(query.message.chat_id, student["current_lesson_order"], context)
