import sys
import os
import logging
from logging.handlers import RotatingFileHandler

# Monkey patch для Python 3.13
if sys.version_info >= (3, 13):
    import warnings
    warnings.warn("Applying monkey patch for Python 3.13 compatibility", RuntimeWarning)
    
    from telegram.ext._updater import Updater
    Updater.__slots__ = tuple(
        s for s in Updater.__slots__ 
        if s != '__weakref__'
    ) + ('_polling_cleanup_cb',)

# Инициализация логгера в самом начале
def setup_logging():
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    os.makedirs("logs", exist_ok=True)
    
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    
    file_handler = RotatingFileHandler(
        os.path.join("logs", "bot.log"),
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setFormatter(logging.Formatter(log_format))
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter(log_format))
    
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    logging.getLogger('httpx').setLevel(logging.WARNING)
    
    return logger

# Инициализируем логгер сразу
root_logger = setup_logging()
logger = logging.getLogger(__name__)

# Проверка существования .env файла
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
logger.info(f"Checking .env file at: {env_path}")

if not os.path.exists(env_path):
    logger.critical(f".env file not found at {env_path}!")
    logger.info("Creating a template .env file...")
    try:
        with open(env_path, 'w') as f:
            f.write("# Add your configuration variables here\n")
            f.write("BOT_TOKEN=your_bot_token_here\n")
            f.write("ENCRYPTION_KEY=your_encryption_key_here\n")
            f.write("SMTP_PASSWORD=your_email_password_here\n")
            f.write("TWILIO_TOKEN=your_twilio_token_here\n")
        logger.info("Template .env file created. Please fill in your credentials.")
        logger.info("🛑 Bot startup aborted. Please configure .env file and restart.")
        # Выходим из скрипта, так как .env отсутствует и был создан шаблон
        sys.exit(1)
    except Exception as e:
        logger.error(f"Error creating .env file: {e}")
        sys.exit(1)
else:
    logger.info(f"Found .env file at {env_path}")

# Теперь можно логировать
logger.info("Logger initialized successfully")

from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, 
    CallbackQueryHandler, ConversationHandler, filters
)
from core.config import config, states
from handlers.base import start, help_command, system_status, cancel, back_handler
import handlers.order_handlers as order_handlers
import handlers.support_handlers as support_handlers
import handlers.performer_handlers as performer_handlers
import handlers.admin_handlers as admin_handlers

def main():
    logger.info("Starting bot...")
    
    # Проверка загрузки конфигурации
    logger.info("Configuration status:")
    logger.info(f"BOT_TOKEN: {'set' if config.BOT_TOKEN else 'NOT SET'}")
    logger.info(f"ENCRYPTION_KEY: {'set' if config.ENCRYPTION_KEY else 'NOT SET'}")
    logger.info(f"SMTP_PASSWORD: {'set' if config.SMTP_PASSWORD else 'NOT SET'}")
    logger.info(f"TWILIO_TOKEN: {'set' if config.TWILIO_TOKEN else 'NOT SET'}")
    
    if not config.BOT_TOKEN:
        logger.critical("BOT_TOKEN is required! Exiting...")
        sys.exit(1)
    
    try:
        os.makedirs(config.BACKUP_DIR, exist_ok=True)
        application = ApplicationBuilder().token(config.BOT_TOKEN).build()
        
        # Базовые обработчики
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(CommandHandler("status", system_status))
        application.add_handler(CommandHandler("cancel", cancel))
        
        # Обработчики заказов
        order_conv_handler = ConversationHandler(
            entry_points=[
                CommandHandler("order", order_handlers.order_command),
                CallbackQueryHandler(order_handlers.new_order_handler, pattern="^new_order$")
            ],
            states={
                states.ASK_DATE: [CallbackQueryHandler(order_handlers.calendar_handler)],
                states.ASK_TIME: [CallbackQueryHandler(order_handlers.time_handler)],
                states.ASK_LOCATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, order_handlers.location_handler)],
                states.ASK_PERFORMERS: [CallbackQueryHandler(order_handlers.performer_handler)],
                states.ASK_PROGRAM: [CallbackQueryHandler(order_handlers.program_handler)],
                states.ASK_PROGRAM_SUB: [CallbackQueryHandler(order_handlers.subprogram_handler)],
                states.ASK_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, order_handlers.amount_handler)],
                states.ASK_DETAILS: [MessageHandler(filters.TEXT & ~filters.COMMAND, order_handlers.details_handler)],
                states.REVIEW_ORDER: [
                    CallbackQueryHandler(order_handlers.confirm_order, pattern="^confirm_order$"),
                    #CallbackQueryHandler(back_handler, pattern="^edit_order$"),
                    CallbackQueryHandler(cancel, pattern="^cancel_order$")
                ],
                states.PERFORMER_FEEDBACK: [CallbackQueryHandler(performer_handlers.handle_reschedule_time)]
            },
            fallbacks=[CommandHandler("cancel", cancel)],
            per_message=True,
            per_user=True,
            conversation_timeout=300
        )
        application.add_handler(order_conv_handler)
        
        # Обработчики поддержки
        support_conv_handler = ConversationHandler(
            entry_points=[
                CommandHandler("support", support_handlers.start_support),
                CallbackQueryHandler(support_handlers.start_support, pattern="^support$")
            ],
            states={
                states.SUPPORT_REQUEST: [MessageHandler(filters.TEXT & ~filters.COMMAND, support_handlers.handle_support_request)],
                states.SUPPORT_CONFIRM: [
                    CallbackQueryHandler(support_handlers.handle_support_confirm, pattern="^support_attach_"),
                    MessageHandler(filters.PHOTO, support_handlers.handle_support_confirm)
                ]
            },
            fallbacks=[CommandHandler("cancel", cancel)],
            per_user=True
        )
        application.add_handler(support_conv_handler)
        
        # Обработчики исполнителей
        application.add_handler(CallbackQueryHandler(
            performer_handlers.handle_performer_response, 
            pattern=r"^(confirm|reject|reschedule)_\d+$"
        ))

        # Администрирование
        application.add_handler(CallbackQueryHandler(
            admin_handlers.admin_panel_handler, 
            pattern="^admin_panel$"
        ))
        application.add_handler(CommandHandler("backup", admin_handlers.backup_database))
        
        # Планировщик задач
        job_queue = application.job_queue
        if job_queue:
            job_queue.run_repeating(admin_handlers.backup_database, interval=86400, first=10)
            job_queue.run_repeating(config.refresh_data, interval=3600, first=0)
        
        logger.info("🚀 Бот успешно запущен")
        application.run_polling()
        
    except Exception as e:
        logger.critical(f"🛑 Критическая ошибка при запуске бота: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()