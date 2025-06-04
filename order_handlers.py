import re
import logging
import datetime
from telegram import Update, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler, MessageHandler, filters
from core.config import config, states
from core.database import db
from core.utils import (
    create_calendar, validate_date, validate_time, 
    validate_amount, create_time_selection_keyboard,
    create_inline_keyboard
)
from services import google_calendar
from services.notifications import notifier

logger = logging.getLogger(__name__)

async def new_order_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    return await order_command(update, context)

async def order_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    now = datetime.datetime.now()
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="📅 <b>Выберите дату для заказа:</b>",
        reply_markup=create_calendar(now.year, now.month),
        parse_mode="HTML"
    )
    return states.ASK_DATE

async def calendar_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data.split('_')
    
    if data[0] == config.CALENDAR_SELECT_DAY_PREFIX:
        year, month, day = map(int, data[1:4])
        selected_date = f"{day:02d}.{month:02d}.{year}"
        
        if not validate_date(selected_date):
            await query.edit_message_text(
                "❌ Неверная дата! Пожалуйста, выберите дату в будущем.",
                reply_markup=create_calendar(year, month)
            )
            return states.ASK_DATE
        
        context.user_data['order_date'] = selected_date
        await query.edit_message_text(
            f"📅 Выбрана дата: *{selected_date}*\n\n⏰ Теперь выберите время:",
            parse_mode="Markdown",
            reply_markup=create_time_selection_keyboard()
        )
        return states.ASK_TIME
    
    year, month = map(int, data[1:3])
    if data[0] == config.CALENDAR_PREV_MONTH_PREFIX:
        month -= 1
        if month == 0:
            month = 12
            year -= 1
    elif data[0] == config.CALENDAR_NEXT_MONTH_PREFIX:
        month += 1
        if month == 13:
            month = 1
            year += 1
    
    await query.edit_message_text(
        "📅 Выберите дату для заказа:",
        reply_markup=create_calendar(year, month)
    )
    return states.ASK_DATE

async def time_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data.split('_')
    
    if data[0] == "time":
        time_slot = data[1]
        date = context.user_data.get('order_date', '')
        
        if not validate_time(date, time_slot):
            await query.edit_message_text(
                "❌ Неверное время! Пожалуйста, выберите корректный временной слот.",
                reply_markup=create_time_selection_keyboard()
            )
            return states.ASK_TIME
        
        context.user_data['order_time'] = time_slot
        await query.edit_message_text(
            f"⏰ Выбрано время: *{time_slot}*\n\n📍 Теперь введите место проведения мероприятия:",
            parse_mode="Markdown"
        )
        return states.ASK_LOCATION
    
    if data[0] == "back":
        now = datetime.datetime.now()
        await query.edit_message_text(
            "📅 Выберите дату для заказа:",
            reply_markup=create_calendar(now.year, now.month)
        )
        return states.ASK_DATE
    
    return states.ASK_TIME

async def location_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    location = update.message.text.strip()
    if len(location) < 5:
        await update.message.reply_text("❌ Слишком короткое название места. Пожалуйста, введите более подробное описание.")
        return states.ASK_LOCATION
    
    context.user_data['order_location'] = location
    await update.message.reply_text(
        f"📍 Место: *{location}*\n\n👨‍🎤 Выберите исполнителя:",
        parse_mode="Markdown",
        reply_markup=create_inline_keyboard(config.PERFORMERS_LIST, "performer", 2)
    )
    return states.ASK_PERFORMERS

async def performer_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    performer = query.data.split('_', 1)[1]
    context.user_data['order_performers'] = performer
    
    date = context.user_data.get('order_date', '')
    time = context.user_data.get('order_time', '')
    
    if performer != "Любой свободный" and not db.is_performer_available(performer, date, time):
        await query.edit_message_text(
            "❌ Этот исполнитель занят в выбранное время. Пожалуйста, выберите другого.",
            reply_markup=create_inline_keyboard(config.PERFORMERS_LIST, "performer", 2)
        )
        return states.ASK_PERFORMERS
    
    await query.edit_message_text(
        f"👨‍🎤 Исполнитель: *{performer}*\n\n🎪 Выберите категорию программы:",
        parse_mode="Markdown",
        reply_markup=create_inline_keyboard(config.PROGRAM_CATEGORIES, "program", 2)
    )
    return states.ASK_PROGRAM

async def program_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    program = query.data.split('_', 1)[1]
    context.user_data['program_category'] = program
    
    sub_categories = config.PROGRAM_SUB_CATEGORIES.get(program, [])
    if sub_categories:
        context.user_data['order_program'] = program
        await query.edit_message_text(
            f"🎪 Категория: *{program}*\n\nВыберите подкатегорию программы:",
            parse_mode="Markdown",
            reply_markup=create_inline_keyboard(sub_categories, "subprogram", 2, True)
        )
        return states.ASK_PROGRAM_SUB
    
    context.user_data['order_program'] = program
    await query.edit_message_text(
        f"🎪 Программа: *{program}*\n\n💰 Введите сумму заказа (например: 5000 или 7500.50):",
        parse_mode="Markdown"
    )
    return states.ASK_AMOUNT

async def subprogram_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "back":
        await query.edit_message_text(
            "🎪 Выберите категорию программы:",
            reply_markup=create_inline_keyboard(config.PROGRAM_CATEGORIES, "program", 2)
        )
        return states.ASK_PROGRAM
    
    subprogram = query.data.split('_', 1)[1]
    program = context.user_data.get('program_category', '')
    context.user_data['order_program'] = f"{program} - {subprogram}"
    
    await query.edit_message_text(
        f"🎪 Подкатегория: *{subprogram}*\n\n💰 Введите сумму заказа (например: 5000 или 7500.50):",
        parse_mode="Markdown"
    )
    return states.ASK_AMOUNT

async def amount_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    amount = update.message.text.strip()
    
    if not validate_amount(amount):
        await update.message.reply_text("❌ Неверный формат суммы! Пожалуйста, введите число (например: 5000 или 7500.50)")
        return states.ASK_AMOUNT
    
    context.user_data['order_amount'] = amount
    await update.message.reply_text(
        f"💰 Сумма: *{amount}*\n\n📝 Введите дополнительные детали заказа:",
        parse_mode="Markdown"
    )
    return states.ASK_DETAILS

async def details_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    details = update.message.text.strip()
    context.user_data['order_details'] = details
    
    order_summary = (
        "📋 *Сводка заказа*\n\n"
        f"📅 Дата: {context.user_data['order_date']}\n"
        f"⏰ Время: {context.user_data['order_time']}\n"
        f"📍 Место: {context.user_data['order_location']}\n"
        f"👨‍🎤 Исполнитель: {context.user_data['order_performers']}\n"
        f"🎪 Программа: {context.user_data['order_program']}\n"
        f"💰 Сумма: {context.user_data['order_amount']}\n"
        f"📝 Детали: {details}\n\n"
        "Подтверждаете заказ?"
    )
    
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Подтвердить", callback_data="confirm_order"),
           # InlineKeyboardButton("✏️ Редактировать", callback_data="edit_order")
        ],
        [InlineKeyboardButton("❌ Отменить", callback_data="cancel_order")]
    ])
    
    await update.message.reply_text(
        order_summary,
        parse_mode="Markdown",
        reply_markup=keyboard
    )
    return states.REVIEW_ORDER

async def confirm_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    order_data = {
        key: context.user_data[key] 
        for key in [
            'order_date', 'order_time', 'order_location', 
            'order_performers', 'order_program', 
            'order_amount', 'order_details'
        ]
    }
    
    user = update.effective_user
    order_data.update({
        'user_id': user.id,
        'user_name': user.full_name,
        'username': user.username
    })
    
    try:
        order_id = db.save_order(order_data)
        context.user_data['order_id'] = order_id
        
        await query.edit_message_text("✅ <b>Заказ успешно создан!</b>", parse_mode="HTML")
        await notify_admin(context, order_data)
        
        if order_data['order_performers'] != "Любой свободный":
            performer = db.get_performer(name=order_data['order_performers'])
            if performer and performer.get('telegram_user_id'):
                await request_performer_confirmation(
                    context, 
                    performer['telegram_user_id'], 
                    order_id
                )
        
        context.job_queue.run_once(
            lambda ctx: google_calendar.sync_order_to_calendar(order_id),
            when=0
        )
    except Exception as e:
        logger.error(f"Ошибка при создании заказа: {e}", exc_info=True)
        await query.edit_message_text(
            "❌ <b>Произошла ошибка при создании заказа.</b> Пожалуйста, попробуйте позже.",
            parse_mode="HTML"
        )
    
    for key in list(context.user_data.keys()):
        if key.startswith('order_') or key == 'program_category':
            del context.user_data[key]
    
    return ConversationHandler.END

async def notify_admin(context: ContextTypes.DEFAULT_TYPE, order_data: dict):
    message = (
        "🆕 *Новый заказ!*\n\n"
        f"👤 Клиент: {order_data['user_name']} (@{order_data['username']})\n"
        f"📅 Дата: {order_data['order_date']}\n"
        f"⏰ Время: {order_data['order_time']}\n"
        f"📍 Место: {order_data['order_location']}\n"
        f"🎭 Исполнитель: {order_data['order_performers']}\n"
        f"🎪 Программа: {order_data['order_program']}\n"
        f"💰 Сумма: {order_data['order_amount']}\n"
        f"📝 Детали: {order_data['order_details']}"
    )
    
    for admin_id in config.ADMIN_IDS:
        try:
            await context.bot.send_message(
                chat_id=admin_id,
                text=message,
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления администратору {admin_id}: {e}")

async def request_performer_confirmation(context: ContextTypes.DEFAULT_TYPE, performer_id: int, order_id: int):
    order = db.get_order(order_id)
    if not order:
        return
    
    message = (
        "🔄 <b>Требуется подтверждение заказа!</b>\n\n"
        f"📅 <b>Дата:</b> {order['order_date']}\n"
        f"⏰ <b>Время:</b> {order['order_time']}\n"
        f"📍 <b>Место:</b> {order['order_location']}\n"
        f"🎭 <b>Программа:</b> {order['order_program']}\n\n"
        "Подтверждаете выполнение заказа?"
    )
    
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Подтвердить", callback_data=f"confirm_{order_id}"),
            InlineKeyboardButton("❌ Отказаться", callback_data=f"reject_{order_id}")
        ],
        [InlineKeyboardButton("🔄 Предложить другое время", callback_data=f"reschedule_{order_id}")]
    ])
    
    try:
        await context.bot.send_message(
            chat_id=performer_id,
            text=message,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Ошибка запроса подтверждения: {e}")