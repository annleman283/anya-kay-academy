import os

# Токен бота, полученный у @BotFather
BOT_TOKEN = os.getenv("BOT_TOKEN", "")

# Telegram user_id администраторов через запятую, например: "123456789,987654321"
# Узнать свой user_id можно у бота @userinfobot
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]

# Путь к файлу базы данных SQLite
DB_PATH = os.getenv("DB_PATH", "lessons.db")

# Доля правильных ответов, необходимая для прохождения теста (1.0 = все ответы верны)
PASS_THRESHOLD = float(os.getenv("PASS_THRESHOLD", "1.0"))

# Через сколько дней бездействия ученице отправляется напоминание
REMINDER_INACTIVE_DAYS = int(os.getenv("REMINDER_INACTIVE_DAYS", "3"))

# Как часто (в секундах) проверять неактивных учениц
REMINDER_CHECK_INTERVAL_SECONDS = int(os.getenv("REMINDER_CHECK_INTERVAL_SECONDS", str(24 * 60 * 60)))

# Файл для сохранения состояния бота (чтобы прогресс теста не терялся при перезапуске)
PERSISTENCE_PATH = os.getenv("PERSISTENCE_PATH", "bot_persistence.pickle")

# URL Telegram Mini App ANYA KAY Academy (Railway public domain, https://...)
ACADEMY_URL = os.getenv("ACADEMY_URL", "").strip()
