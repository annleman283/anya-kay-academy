# ANYA KAY Academy v2.0 COMPLETE

Сборка создана на КОПИИ `lessons_backup.db`; исходный backup и старый Telegram-бот не изменялись.

## Уже внутри
- Реальная база уроков 0–8 из backup.
- Добавлены уроки 9–13, YouTube-ссылки, презентации и тесты из переданных файлов.
- 14 уроков (0–13), 99 тестовых вопросов.
- YouTube смотрится внутри Mini App через встроенный privacy-enhanced player.
- Презентации 9–13: просмотр внутри приложения через PDF-preview + скачивание оригинального PPTX.
- Правильные ответы не передаются в интерфейс до проверки; варианты и порядок вопросов перемешиваются.
- Обязательная регистрация имени/фамилии латиницей.
- Экскурсия по приложению при первом запуске + повтор из профиля.
- `Мой график` как отдельная вкладка; данные индивидуальны для каждой ученицы.
- `Задать вопрос Ане` ведёт в личный Telegram `@anyalashkey`.
- Заметки, сохранённое, ошибки, аналитика, финальный экзамен, сертификат.

## Важно перед Railway
1. Не подключать эту сборку сразу к боевой DB старого бота. Сначала тестировать `lessons.db` из архива.
2. `BOT_TOKEN` нужен тот же, если старые материалы 0–8 хранятся как Telegram `file_id`.
3. `ADMIN_IDS` — Telegram ID Ани через запятую.
4. `DEV_USER_ID` можно временно указать для браузерного теста регистрации/прогресса; в production убрать.
5. `PASS_THRESHOLD=1.0` означает 100% правильных ответов для прохождения урока.

## Урок 14
`Дезинфекция и стерилизация инструментов` намеренно не добавлен: Аня загрузит его позже.

## Запуск локально
`python academy_server.py`

Health check: `/health`

## v2.1 GitHub Ready
This package was optimized for browser upload to GitHub. Large lesson presentations and PDF previews were compressed while keeping the same filenames and application paths. Students still get in-app preview and download buttons. YouTube videos remain embedded in the lesson screen.


## Web-upload build
This build keeps presentation previews/downloads as compact PDFs so the repository can be uploaded through GitHub in the browser. Original PPTX files are intentionally excluded from Git. They can later be stored in external object storage without changing lesson content.
