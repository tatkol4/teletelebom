import logging
from telegram import Update
from telegram.ext import ContextTypes, CallbackQueryHandler
from core.config import config, states
from core.database import db
from services.notifications import notifier
from core.utils import create_time_selection_keyboard

logger = logging.getLogger(__name__)

async def handle_performer_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data.split('_')
    action = data[0]
    order_id = int(data[1])
    
    if action == "confirm":
        db.update_order_status(order_id, "confirmed")
        await query.edit_message_text("✅ Заказ подтвержден!")
        
        order = db.get_order(order_id)
        if order:
            await notifier.send_notification(
                order['user_id'], 
                "🎉 Ваш заказ подтвержден исполнителем!",
                context,
                ["telegram"]
            )
    
    elif action == "reject":
        db.update_order_status(order_id, "rejected")
        await query.edit_message_text("❌ Вы отказались от заказа.")
        await find_replacement_performer(context, order_id)
    
    elif action == "reschedule":
        context.user_data['reschedule_order_id'] = order_id
        await query.edit_message_text(
            "🕒 Выберите новое время для заказа:",
            reply_markup=create_time_selection_keyboard(order_id)
        )
        return states.PERFORMER_FEEDBACK

async def handle_reschedule_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data.split('_')
    order_id = int(data[1])
    new_time = data[2]
    
    with db.session_scope() as session:
        order = session.query(Order).get(order_id)
        if order:
            order.order_time = new_time
            session.commit()
    
    order = db.get_order(order_id)
    if order:
        await notifier.send_notification(
            order['user_id'],
            f"🕒 Время вашего заказа изменено на {new_time}",
            context,
            ["telegram"]
        )
    
    await query.edit_message_text(f"✅ Время заказа изменено на {new_time}")
    return ConversationHandler.END

async def find_replacement_performer(context: ContextTypes.DEFAULT_TYPE, order_id: int):
    order = db.get_order(order_id)
    if not order:
        return
    
    logger.info(f"Поиск замены для заказа #{order_id}")
    await notifier.send_notification(
        config.ADMIN_IDS[0],
        f"⚠️ Требуется замена исполнителя для заказа #{order_id}",
        context,
        ["telegram"]
    )