import logging

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
    MessageHandler,
    PicklePersistence,
    filters,
)

import keyboards as kb
import config
import database as db
from handlers import student, admin

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)


async def route_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if admin.is_admin(update.effective_user.id):
        await admin.admin_start(update, context)
    else:
        await student.start(update, context)


async def fallback_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message is None:
        return
    if admin.is_admin(update.effective_user.id):
        await update.message.reply_text(
            "Пожалуйста, воспользуйтесь кнопками меню внизу экрана 👇", reply_markup=kb.admin_menu()
        )
    else:
        await student.fallback_message(update, context)


async def remind_inactive_students(context: ContextTypes.DEFAULT_TYPE):
    inactive = db.get_inactive_students(config.REMINDER_INACTIVE_DAYS)
    for row in inactive:
        try:
            chat = await context.bot.get_chat(row["user_id"])
            await context.bot.send_message(
                row["user_id"],
                student.REMINDER_MSG.format(
                    first_name=chat.first_name, days=config.REMINDER_INACTIVE_DAYS
                ),
                reply_markup=kb.next_lesson_kb(),
            )
        except Exception as e:
            logging.warning(f"Не удалось отправить напоминание {row['user_id']}: {e}")
        db.mark_reminded(row["user_id"])


def build_app() -> Application:
    if not config.BOT_TOKEN:
        raise RuntimeError("Переменная окружения BOT_TOKEN не задана!")

    persistence = PicklePersistence(filepath=config.PERSISTENCE_PATH)
    application = Application.builder().token(config.BOT_TOKEN).persistence(persistence).build()

    # ---------- Старт (роутинг админ / ученица) ----------
    application.add_handler(CommandHandler("start", route_start))

    # ---------- Диалог: добавление урока ----------
    add_lesson_conv = ConversationHandler(
        entry_points=[
            CommandHandler("addlesson", admin.add_lesson_start),
            MessageHandler(filters.Text([kb.ADMIN_MENU_ADD_LESSON]), admin.add_lesson_start),
        ],
        states={
            admin.TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin.add_lesson_title)],
            admin.DESCRIPTION: [
                CallbackQueryHandler(admin.add_lesson_description_skip, pattern=r"^skip_description$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin.add_lesson_description),
            ],
            admin.VIDEO_CHOICE: [CallbackQueryHandler(admin.video_choice_callback, pattern=r"^vid_(file|link)$")],
            admin.VIDEO_FILE: [MessageHandler(filters.VIDEO | filters.Document.VIDEO, admin.add_lesson_video_file)],
            admin.VIDEO_LINK: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin.add_lesson_video_link)],
            admin.MATERIALS_MENU: [
                CallbackQueryHandler(admin.materials_menu_callback, pattern=r"^(add_material|add_material_link|materials_done)$")
            ],
            admin.MATERIAL_FILE: [MessageHandler(filters.Document.ALL | filters.VIDEO, admin.add_material_file)],
            admin.MATERIAL_LINK: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin.add_material_link_text)],
            admin.MATERIAL_CAPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin.add_material_caption)],
            admin.Q_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin.add_question_text)],
            admin.Q_PHOTO: [
                CallbackQueryHandler(admin.question_photo_choice, pattern=r"^(add_q_photo|skip_q_photo)$"),
                MessageHandler(filters.PHOTO, admin.question_photo_received),
            ],
            admin.Q_OPTIONS: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin.add_question_options)],
            admin.Q_CORRECT: [CallbackQueryHandler(admin.add_question_correct, pattern=r"^correct:")],
            admin.Q_EXPLANATION: [
                CallbackQueryHandler(admin.add_question_explanation_skip, pattern=r"^skip_explanation$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin.add_question_explanation),
            ],
            admin.Q_MENU: [
                CallbackQueryHandler(admin.question_menu_callback, pattern=r"^(more_question|finish_lesson)$")
            ],
        },
        fallbacks=[
            CommandHandler("cancel", admin.add_lesson_cancel),
            CallbackQueryHandler(admin.confirm_cancel_lesson_callback, pattern=r"^confirm_cancel_lesson$"),
            CallbackQueryHandler(admin.keep_editing_lesson_callback, pattern=r"^keep_editing_lesson$"),
        ],
    )
    application.add_handler(add_lesson_conv)

    # ---------- Диалог: заменить видео существующего урока ----------
    replace_video_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin.replace_video_start, pattern=r"^replace_video:")],
        states={
            admin.RV_CHOICE: [CallbackQueryHandler(admin.replace_video_choice, pattern=r"^vid_(file|link)$")],
            admin.RV_FILE: [MessageHandler(filters.VIDEO | filters.Document.VIDEO, admin.replace_video_file)],
            admin.RV_LINK: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin.replace_video_link)],
        },
        fallbacks=[CommandHandler("cancel", admin.generic_cancel)],
    )
    application.add_handler(replace_video_conv)

    # ---------- Диалог: изменить название/описание урока ----------
    edit_title_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin.edit_title_start, pattern=r"^edit_title:")],
        states={
            admin.ET_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin.edit_title_save)],
            admin.ET_DESC: [
                CallbackQueryHandler(admin.edit_desc_skip, pattern=r"^skip_edit_description$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin.edit_desc_save),
            ],
        },
        fallbacks=[CommandHandler("cancel", admin.generic_cancel)],
    )
    application.add_handler(edit_title_conv)

    # ---------- Диалог: добавить файл к существующему уроку ----------
    add_material_existing_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(admin.add_material_existing_start, pattern=r"^add_material_existing:"),
            CallbackQueryHandler(admin.add_link_existing_start, pattern=r"^add_link_existing:"),
        ],
        states={
            admin.EM_FILE: [MessageHandler(filters.Document.ALL | filters.VIDEO, admin.add_material_existing_file)],
            admin.EM_LINK: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin.add_link_existing_text)],
            admin.EM_CAPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin.add_material_existing_caption)],
        },
        fallbacks=[CommandHandler("cancel", admin.generic_cancel)],
    )
    application.add_handler(add_material_existing_conv)

    # ---------- Диалог: редактировать/добавить вопрос ----------
    qedit_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(admin.qedit_add_start, pattern=r"^add_question_existing:"),
            CallbackQueryHandler(admin.qedit_edit_start, pattern=r"^edit_question:"),
        ],
        states={
            admin.QE_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin.qedit_text)],
            admin.QE_PHOTO: [
                CallbackQueryHandler(admin.qedit_photo_choice, pattern=r"^(add_q_photo|skip_q_photo)$"),
                MessageHandler(filters.PHOTO, admin.qedit_photo_received),
            ],
            admin.QE_OPTIONS: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin.qedit_options)],
            admin.QE_CORRECT: [CallbackQueryHandler(admin.qedit_correct, pattern=r"^correct:")],
            admin.QE_EXPLANATION: [
                CallbackQueryHandler(admin.qedit_explanation_skip, pattern=r"^skip_qedit_explanation$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin.qedit_explanation),
            ],
        },
        fallbacks=[CommandHandler("cancel", admin.generic_cancel)],
    )
    application.add_handler(qedit_conv)

    # ---------- Диалог: редактировать текст/файл материала или гайда ----------
    edit_field_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(admin.edit_material_start, pattern=r"^edit_material:"),
            CallbackQueryHandler(admin.edit_bonus_start, pattern=r"^edit_bonus:"),
        ],
        states={
            admin.EF_CHOICE: [CallbackQueryHandler(admin.edit_field_choice_callback, pattern=r"^ef_(text|file|link)$")],
            admin.EF_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin.edit_field_text)],
            admin.EF_FILE: [MessageHandler(filters.Document.ALL | filters.VIDEO, admin.edit_field_file)],
            admin.EF_LINK: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin.edit_field_link)],
        },
        fallbacks=[CommandHandler("cancel", admin.generic_cancel)],
    )
    application.add_handler(edit_field_conv)

    # ---------- Диалог: бонусные гайды ----------
    bonus_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(admin.bonus_menu_callback, pattern=r"^(bonus_add|bonus_add_link|bonus_list)$"),
            CallbackQueryHandler(admin.bonus_add_more_callback, pattern=r"^(bonus_more|bonus_add_done)$"),
        ],
        states={
            admin.BONUS_MENU_CHOICE: [
                CallbackQueryHandler(admin.bonus_menu_callback, pattern=r"^(bonus_add|bonus_add_link|bonus_list)$")
            ],
            admin.BONUS_FILE: [MessageHandler(filters.Document.ALL | filters.VIDEO, admin.bonus_add_file)],
            admin.BONUS_LINK: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin.bonus_add_link_text)],
            admin.BONUS_CAPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin.bonus_add_caption)],
        },
        fallbacks=[CommandHandler("cancel", admin.generic_cancel)],
    )
    application.add_handler(bonus_conv)

    # ---------- Постоянное меню (кнопки внизу экрана) ----------
    application.add_handler(MessageHandler(filters.Text([kb.STUDENT_MENU_LESSONS]), student.all_lessons_menu))
    application.add_handler(MessageHandler(filters.Text([kb.STUDENT_MENU_PROGRESS]), student.progress_menu))
    application.add_handler(MessageHandler(filters.Text([kb.STUDENT_MENU_GUIDES]), student.guides_menu))
    application.add_handler(MessageHandler(filters.Text([kb.STUDENT_MENU_HELP]), student.help_menu))

    application.add_handler(MessageHandler(filters.Text([kb.ADMIN_MENU_LESSONS]), admin.list_lessons))
    application.add_handler(MessageHandler(filters.Text([kb.ADMIN_MENU_GUIDES]), admin.bonus_menu))
    application.add_handler(MessageHandler(filters.Text([kb.ADMIN_MENU_STUDENTS]), admin.list_students))
    application.add_handler(MessageHandler(filters.Text([kb.ADMIN_MENU_BACKUP]), admin.backup))
    application.add_handler(MessageHandler(filters.Text([kb.ADMIN_MENU_TEST_MODE]), admin.test_mode_reset))

    # ---------- Прочие команды (запасной вариант, если кто-то печатает вручную) ----------
    application.add_handler(CommandHandler("lessons", admin.list_lessons))
    application.add_handler(CommandHandler("students", admin.list_students))
    application.add_handler(CommandHandler("backup", admin.backup))

    # ---------- Callback-кнопки: обучение ----------
    application.add_handler(CallbackQueryHandler(student.begin_learning_callback, pattern=r"^begin_learning$"))
    application.add_handler(CallbackQueryHandler(student.start_quiz_callback, pattern=r"^start_quiz:"))
    application.add_handler(CallbackQueryHandler(student.answer_callback, pattern=r"^ans:"))
    application.add_handler(CallbackQueryHandler(student.next_lesson_callback, pattern=r"^next_lesson$"))
    application.add_handler(CallbackQueryHandler(student.rewatch_callback, pattern=r"^rewatch:"))
    application.add_handler(CallbackQueryHandler(student.open_lesson_callback, pattern=r"^open_lesson:"))

    # ---------- Callback-кнопки: управление уроками ----------
    application.add_handler(CallbackQueryHandler(admin.manage_lesson_callback, pattern=r"^manage_lesson:"))
    application.add_handler(CallbackQueryHandler(admin.back_to_lessons_callback, pattern=r"^back_to_lessons$"))
    application.add_handler(CallbackQueryHandler(admin.preview_lesson_callback, pattern=r"^preview_lesson:"))
    application.add_handler(CallbackQueryHandler(admin.delete_lesson_callback, pattern=r"^delete_lesson:"))
    application.add_handler(CallbackQueryHandler(admin.confirm_delete_lesson_callback, pattern=r"^confirm_delete_lesson:"))
    application.add_handler(CallbackQueryHandler(admin.cancel_delete_callback, pattern=r"^cancel_delete$"))
    application.add_handler(CallbackQueryHandler(admin.manage_materials_callback, pattern=r"^manage_materials:"))
    application.add_handler(CallbackQueryHandler(admin.delete_material_callback, pattern=r"^delete_material:"))
    application.add_handler(CallbackQueryHandler(admin.delete_bonus_callback, pattern=r"^delete_bonus:"))
    application.add_handler(CallbackQueryHandler(admin.manage_questions_callback, pattern=r"^manage_questions:"))
    application.add_handler(CallbackQueryHandler(admin.delete_question_callback, pattern=r"^delete_question:"))
    application.add_handler(CallbackQueryHandler(admin.confirm_delete_question_callback, pattern=r"^confirm_delete_question:"))
    application.add_handler(CallbackQueryHandler(admin.student_detail_callback, pattern=r"^student_detail:"))

    # ---------- Напоминания неактивным ученицам ----------
    if application.job_queue is not None:
        application.job_queue.run_repeating(
            remind_inactive_students,
            interval=config.REMINDER_CHECK_INTERVAL_SECONDS,
            first=60,
        )
    else:
        logging.warning(
            "JobQueue недоступен — напоминания работать не будут. "
            "Установите зависимость: pip install \"python-telegram-bot[job-queue]\""
        )

    # ---------- Заглушка на непонятные сообщения (регистрируем ПОСЛЕДНЕЙ) ----------
    application.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, fallback_message))

    return application


def main():
    db.init_db()
    app = build_app()
    logging.info("Бот запущен, ожидаю сообщения...")
    app.run_polling(allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    main()
