import logging
import asyncio
from email.mime.text import MIMEText
from concurrent.futures import ThreadPoolExecutor
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException
from core.config import config
from telegram.constants import ParseMode
from core.database import db
from core.security import encrypt_data, decrypt_data  # Предполагается реализация

logger = logging.getLogger(__name__)

class NotificationManager:
    def __init__(self):
        self.twilio_client = None
        self.executor = ThreadPoolExecutor(max_workers=5)
        self.rate_limit_cache = {}
        
        # Инициализация Twilio с задержкой
        self._init_twilio()
    
    def _init_twilio(self):
        """Асинхронная инициализация Twilio"""
        if config.TWILIO_SID and config.TWILIO_TOKEN:
            try:
                # Дешифруем токен, если он зашифрован
                decrypted_token = decrypt_data(config.TWILIO_TOKEN)
                self.twilio_client = Client(config.TWILIO_SID, decrypted_token)
                logger.info("Twilio client initialized")
            except Exception as e:
                logger.error(f"Error initializing Twilio: {e}")
    
    def _check_rate_limit(self, channel: str, recipient: str) -> bool:
        """Проверка ограничения частоты отправки"""
        key = f"{channel}:{recipient}"
        current_time = asyncio.get_event_loop().time()
        
        # Получаем историю отправок
        last_sent = self.rate_limit_cache.get(key, [])
        
        # Фильтруем старые записи (окно 1 час)
        recent_sent = [t for t in last_sent if current_time - t < 3600]
        
        # Проверяем лимит (не более 5 сообщений в час)
        if len(recent_sent) >= 5:
            logger.warning(f"Rate limit exceeded for {key}")
            return False
        
        # Обновляем кэш
        recent_sent.append(current_time)
        self.rate_limit_cache[key] = recent_sent
        return True
    
    async def _run_in_thread(self, func, *args, **kwargs):
        """Асинхронный запуск синхронных функций"""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self.executor, lambda: func(*args, **kwargs))
    
    async def send_sms(self, phone: str, message: str):
        """Асинхронная отправка SMS через Twilio"""
        if not self.twilio_client:
            logger.warning("Twilio client not initialized")
            return False
        
        if not self._check_rate_limit("sms", phone):
            return False
        
        try:
            await self._run_in_thread(
                self.twilio_client.messages.create,
                body=message,
                from_=config.TWILIO_NUMBER,
                to=phone
            )
            logger.info(f"SMS sent to {phone}")
            return True
        except TwilioRestException as e:
            logger.error(f"Twilio error: {e.msg}")
        except Exception as e:
            logger.error(f"Unexpected SMS error: {e}")
        return False
    
    async def send_whatsapp(self, phone: str, message: str):
        """Асинхронная отправка WhatsApp через Twilio"""
        if not self.twilio_client:
            logger.warning("Twilio client not initialized")
            return False
        
        if not self._check_rate_limit("whatsapp", phone):
            return False
        
        try:
            await self._run_in_thread(
                self.twilio_client.messages.create,
                body=message,
                from_=f"whatsapp:{config.TWILIO_NUMBER}",
                to=f"whatsapp:{phone}"
            )
            logger.info(f"WhatsApp sent to {phone}")
            return True
        except TwilioRestException as e:
            logger.error(f"Twilio error: {e.msg}")
        except Exception as e:
            logger.error(f"Unexpected WhatsApp error: {e}")
        return False
    
    async def send_email(self, email: str, subject: str, message: str):
        """Асинхронная отправка email"""
        if not all([config.SMTP_SERVER, config.SMTP_USER, config.SMTP_PASSWORD]):
            logger.warning("SMTP not configured")
            return False
        
        if not self._check_rate_limit("email", email):
            return False
        
        try:
            # Дешифруем SMTP пароль
            from core.security import decrypt_data
            smtp_password = decrypt_data(config.SMTP_PASSWORD)
            
            msg = MIMEText(message, 'html')
            msg['Subject'] = subject
            msg['From'] = config.SMTP_FROM
            msg['To'] = email
            
            # Асинхронная отправка через thread pool
            await self._run_in_thread(
                self._sync_send_email,
                msg,
                smtp_password
            )
            logger.info(f"Email sent to {email}")
            return True
        except Exception as e:
            logger.error(f"Email sending error: {e}")
        return False
    
    def _sync_send_email(self, msg, smtp_password):
        """Синхронная отправка email (выполняется в thread pool)"""
        with smtplib.SMTP(config.SMTP_SERVER, config.SMTP_PORT) as server:
            server.starttls()
            server.login(config.SMTP_USER, smtp_password)
            server.send_message(msg)
    
    async def send_telegram(self, user_id: int, message: str, context):
        """Отправка Telegram сообщения"""
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=message,
                parse_mode=ParseMode.HTML
            )
            logger.info(f"Telegram message sent to {user_id}")
            return True
        except Exception as e:
            logger.error(f"Telegram send error: {e}")
        return False
    
    async def send_notification(
        self,
        user_id: int,
        message: str,
        context,
        channels: list = ["telegram"],
        max_retries: int = 2,
        retry_delay: float = 1.0
    ):
        """Отправка уведомления с повторными попытками"""
        # Убираем зависимость от модели User
        for attempt in range(1, max_retries + 1):
            success = True
            
            for channel in channels:
                channel_success = False
                
                try:
                    if channel == "telegram":
                        channel_success = await self.send_telegram(user_id, message, context)
                    elif channel == "sms":
                        # Для SMS нужен номер телефона - упрощаем логику
                        channel_success = await self.send_sms(str(user_id), message)
                    elif channel == "whatsapp":
                        channel_success = await self.send_whatsapp(str(user_id), message)
                    elif channel == "email":
                        # Для email нужен адрес - упрощаем
                        channel_success = await self.send_email(
                            f"{user_id}@example.com",  # В реальной системе нужно получать email
                            "Уведомление от EventBot",
                            message
                        )
                except Exception as e:
                    logger.error(f"Channel {channel} error: {e}")
                    channel_success = False
                
                success = success and channel_success
            
            if success:
                return True
            
            # Экспоненциальная задержка перед повторной попыткой
            delay = retry_delay * (2 ** (attempt - 1))
            logger.warning(f"Retry {attempt}/{max_retries} in {delay}s")
            await asyncio.sleep(delay)
        
        logger.error(f"Failed to send notification after {max_retries} attempts")
        return False

# Инициализируем менеджер уведомлений
notifier = NotificationManager()