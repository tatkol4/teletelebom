import logging
import os
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove
from telegram.ext import (
    ContextTypes, 
    CallbackQueryHandler, 
    MessageHandler, 
    filters, 
    ConversationHandler
)
from core.config import config, states
from core.database import db
from services.notifications import notifier
from models.support_ticket import SupportTicket  # Импорт модели

logger = logging.getLogger(__name__)

async def start_support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.message.reply_text(
            "📝 Опишите вашу проблему или вопрос:",
            reply_markup=ReplyKeyboardRemove()
        )
    else:
        await update.message.reply_text(
            "📝 Опишите вашу проблему или вопрос:",
            reply_markup=ReplyKeyboardRemove()
        )
    
    return states.SUPPORT_REQUEST

async def handle_support_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_message = update.message.text.strip()
        user = update.effective_user
        
        ticket_id = db.create_support_ticket(
            user_id=user.id,
            message=user_message,
            user_name=user.full_name,
            username=user.username
        )
        
        if not ticket_id:
            await update.message.reply_text("❌ Произошла ошибка при создании запроса")
            return ConversationHandler.END
        
        context.user_data['ticket_id'] = ticket_id
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Да", callback_data="support_attach_yes")],
            [InlineKeyboardButton("❌ Нет", callback_data="support_attach_no")]
        ])
        
        await update.message.reply_text(
            "✅ Ваш запрос получен! Хотите приложить скриншот?",
            reply_markup=keyboard
        )
        
        return states.SUPPORT_CONFIRM
    
    except Exception as e:
        logger.error(f"Error in handle_support_request: {e}", exc_info=True)
        await update.message.reply_text("❌ Произошла ошибка при обработке вашего запроса")
        return ConversationHandler.END

async def handle_support_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if update.callback_query:
            # Обработка кнопок "Да/Нет" для прикрепления скриншота
            query = update.callback_query
            await query.answer()
            choice = query.data.split('_')[-1]
            
            if choice == "yes":
                await query.edit_message_text("📎 Пришлите скриншот:")
                return states.SUPPORT_CONFIRM
            else:
                ticket_id = context.user_data['ticket_id']
                await finalize_support_request(context, ticket_id)
                await query.edit_message_text("🛎 Ваш запрос передан в поддержку. Мы ответим в ближайшее время!")
                return ConversationHandler.END
        else:
            # Обработка сообщения с фото
            ticket_id = context.user_data.get('ticket_id')
            if not ticket_id:
                await update.message.reply_text("❌ Не удалось идентифицировать ваш запрос")
                return ConversationHandler.END
            
            # Проверяем, есть ли фото в сообщении
            if update.message.photo:
                # Получаем фото с наивысшим разрешением
                photo = update.message.photo[-1]
                file = await photo.get_file()
                
                # =====================================================================
                # ШАГ 1: СКАЧИВАЕМ ФОТО В ПАМЯТЬ И СОЗДАЕМ БАЙТОВЫЙ МАССИВ
                # =====================================================================
                photo_bytes = await file.download_as_bytearray()
                original_size = len(photo_bytes)  # Сохраняем оригинальный размер для логов
                
                # =====================================================================
                # ШАГ 2: СЖАТИЕ ИЗОБРАЖЕНИЯ (ЕСЛИ УСТАНОВЛЕНА BIBLIOTHEK PILLOW)
                # =====================================================================
                try:
                    # Пытаемся импортировать Pillow (если установлен)
                    from PIL import Image
                    import io
                    
                    # Открываем изображение из байтов
                    img = Image.open(io.BytesIO(photo_bytes))
                    
                    # Уменьшаем размер, если изображение слишком большое
                    MAX_WIDTH, MAX_HEIGHT = 1920, 1080
                    if img.width > MAX_WIDTH or img.height > MAX_HEIGHT:
                        # Сохраняем пропорции
                        img.thumbnail((MAX_WIDTH, MAX_HEIGHT), Image.LANCZOS)
                        logger.info(f"Resized image to {img.width}x{img.height}")
                    
                    # Конвертируем в JPEG, если это другой формат
                    if img.format != 'JPEG':
                        img = img.convert('RGB')
                    
                    # Сжимаем с качеством 85%
                    output_buffer = io.BytesIO()
                    img.save(output_buffer, format='JPEG', quality=85, optimize=True)
                    compressed_bytes = output_buffer.getvalue()
                    
                    # Используем сжатые байты, если они действительно меньше
                    if len(compressed_bytes) < original_size:
                        photo_bytes = compressed_bytes
                        logger.info(f"Compressed image: {original_size} -> {len(compressed_bytes)} bytes")
                    else:
                        logger.info("Compressed image not smaller, using original")
                        
                except ImportError:
                    logger.warning("Pillow not installed, skipping compression")
                except Exception as compression_error:
                    logger.warning(f"Image compression failed: {compression_error}")
                # =====================================================================
                
                # =====================================================================
                # ШАГ 3: СОХРАНЕНИЕ ФОТО (S3 ИЛИ ЛОКАЛЬНО)
                # =====================================================================
                photo_path = None
                
                # Вариант 1: Загрузка в AWS S3 (если настроены ключи)
                if config.S3_ENABLED:
                    try:
                        import boto3
                        
                        # Создаем клиент S3
                        s3_client = boto3.client(
                            's3',
                            region_name=config.S3_REGION,
                            aws_access_key_id=config.AWS_ACCESS_KEY,
                            aws_secret_access_key=config.AWS_SECRET_KEY
                        )
                        
                        # Генерируем уникальный ключ для файла
                        s3_key = f"support/{ticket_id}.jpg"
                        
                        # Загружаем напрямую из памяти в S3
                        s3_client.upload_fileobj(
                            io.BytesIO(photo_bytes),
                            config.S3_BUCKET,
                            s3_key,
                            ExtraArgs={
                                'ContentType': 'image/jpeg',
                                'ACL': 'private'
                            }
                        )
                        
                        photo_path = s3_key
                        logger.info(f"Uploaded to S3: s3://{config.S3_BUCKET}/{s3_key}")
                        
                    except Exception as s3_error:
                        logger.error(f"S3 upload failed: {s3_error}")
                
                # Вариант 2: Локальное сохранение (если S3 не настроен или произошла ошибка)
                if not photo_path:
                    try:
                        # Создаем директорию для вложений, если ее нет
                        os.makedirs("support_attachments", exist_ok=True)
                        file_path = os.path.join("support_attachments", f"{ticket_id}.jpg")
                        
                        # Сохраняем файл на диск
                        with open(file_path, 'wb') as f:
                            f.write(photo_bytes)
                        
                        photo_path = file_path
                        logger.info(f"Saved locally: {file_path}")
                        
                    except Exception as file_error:
                        logger.error(f"Local file save failed: {file_error}")
                # =====================================================================
                
                # =====================================================================
                # ШАГ 4: ОБНОВЛЕНИЕ ТИКЕТА В БАЗЕ ДАННЫХ
                # =====================================================================
                if photo_path:
                    with db.session_scope() as session:
                        ticket = session.query(SupportTicket).get(ticket_id)
                        if ticket:
                            ticket.photo_path = photo_path
                            session.commit()
                            logger.info(f"Updated ticket {ticket_id} with photo path")
                else:
                    logger.error("Failed to save photo for ticket {ticket_id}")
                # =====================================================================
            else:
                logger.warning("Photo message without actual photo")
            
            # Завершаем обработку запроса
            await finalize_support_request(context, ticket_id)
            await update.message.reply_text("✅ Скриншот получен! Запрос передан в поддержку.")
            return ConversationHandler.END
    
    except Exception as e:
        logger.error(f"Error in handle_support_confirm: {e}", exc_info=True)
        await update.message.reply_text("❌ Произошла ошибка при обработке вашего запроса")
        return ConversationHandler.END

async def finalize_support_request(context: ContextTypes.DEFAULT_TYPE, ticket_id: int):
    try:
        ticket = db.get_support_ticket(ticket_id)
        if not ticket:
            logger.error(f"Ticket {ticket_id} not found in database")
            return
        
        message = (
            "🆘 <b>Новый запрос в поддержку!</b>\n\n"
            f"🆔 ID: {ticket_id}\n"
            f"👤 Пользователь: {ticket['user_name']} (@{ticket['username']})\n"
            f"📅 Дата: {ticket['created_at']}\n\n"
            f"✉️ <b>Сообщение:</b>\n{ticket['message']}"
        )
        
        # Добавляем информацию о фото
        if ticket.get('photo_path'):
            message += "\n\n📸 К сообщению прикреплен скриншот"
        
        for operator_id in config.SUPPORT_OPERATORS:
            try:
                await context.bot.send_message(
                    chat_id=operator_id,
                    text=message,
                    parse_mode="HTML"
                )
                
                # Если есть фото, отправляем его
                if ticket.get('photo_path'):
                    with open(ticket['photo_path'], 'rb') as photo_file:
                        await context.bot.send_photo(
                            chat_id=operator_id,
                            photo=photo_file,
                            caption=f"Скриншот для тикета #{ticket_id}"
                        )
            except Exception as e:
                logger.error(f"Error sending request to operator {operator_id}: {e}")
        
    except Exception as e:
        logger.error(f"Error in finalize_support_request: {e}", exc_info=True)