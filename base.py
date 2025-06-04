from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler
from core.config import config, states
from core.utils import main_menu_keyboard
import logging

logger = logging.getLogger(__name__)

async def back_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик кнопки 'Назад'"""
    query = update.callback_query
    await query.answer()
    
    # Здесь должна быть логика возврата к предыдущему шагу
    # Например:
    current_state = context.user_data.get('current_state', states.ASK_DATE)
    
    if current_state == states.REVIEW_ORDER:
        await query.edit_message_text("📝 Введите дополнительные детали заказа:")
        return states.ASK_DETAILS
    
    # Для других состояний - возврат на шаг назад
    return current_state - 1


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text(
        f"Привет, {user.first_name}! Чем могу помочь?",
        reply_markup=main_menu_keyboard(user.id in config.ADMIN_IDS)
    )
    return ConversationHandler.END

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "ℹ️ *Доступные команды:*\n"
        "/start - начать работу\n"
        "/order - создать заказ\n"
        "/support - связаться с поддержкой\n"
        "/cancel - отменить текущую операцию\n"
        "/help - показать справку",
        parse_mode="Markdown"
    )

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text(
        "❌ Операция отменена.",
        reply_markup=main_menu_keyboard(user.id in config.ADMIN_IDS)
    )
    context.user_data.clear()
    return ConversationHandler.END

async def system_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ Бот работает в штатном режиме")