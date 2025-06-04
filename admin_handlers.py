import logging
from telegram import Update
from telegram.ext import ContextTypes, CallbackQueryHandler
from core.database import db
from core.config import config, states

logger = logging.getLogger(__name__)

async def admin_panel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("⚙️ Админ-панель в разработке")

async def backup_database(context: ContextTypes.DEFAULT_TYPE):
    try:
        backup_path = db.create_backup()
        logger.info(f"Создана резервная копия базы данных: {backup_path}")
    except Exception as e:
        logger.error(f"Ошибка при создании резервной копии: {e}")

def cleanup_attachments(max_age_days=30):
    now = datetime.now()
    for filename in os.listdir("support_attachments"):
        file_path = os.path.join("support_attachments", filename)
        file_time = datetime.fromtimestamp(os.path.getmtime(file_path))
        if (now - file_time).days > max_age_days:
            os.remove(file_path)