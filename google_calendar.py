import logging
import json
import asyncio
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from core.database import db
from core.config import config
from core.utils import validate_date_time_format  # Новая функция валидации
from models.performer import Performer  # Импорт модели
from models.order import Order  # Импорт модели

logger = logging.getLogger(__name__)

# Кэш сервисов для производительности
SERVICE_CACHE = {}

def get_calendar_service(user_id: int):
    """Возвращает сервис Google Calendar для пользователя, используя кэш"""
    # Проверка кэша
    if user_id in SERVICE_CACHE:
        return SERVICE_CACHE[user_id]
    
    # Получение данных исполнителя
    performer = db.get_performer_by_user_id(user_id)
    if not performer:
        logger.warning(f"Performer not found for user_id: {user_id}")
        return None
    
    # Проверка токенов
    if not performer.get('google_tokens'):
        logger.warning(f"No Google tokens for performer: {performer['id']}")
        return None
    
    try:
        # Десериализация токенов
        tokens = json.loads(performer['google_tokens'])
        
        # Создание учетных данных
        creds = Credentials.from_authorized_user_info(tokens)
        
        # Создание сервиса календаря
        service = build(
            'calendar', 
            'v3', 
            credentials=creds,
            cache_discovery=False  # Ускоряет создание сервиса
        )
        
        # Сохранение в кэш
        SERVICE_CACHE[user_id] = service
        return service
    
    except (json.JSONDecodeError, TypeError) as e:
        logger.error(f"Invalid Google tokens JSON (user {user_id}): {e}")
    except Exception as e:
        logger.error(f"Error creating Google Calendar service: {e}")
    
    return None

async def sync_order_to_calendar(order_id: int):
    """Асинхронная синхронизация заказа с Google Calendar"""
    # Получаем данные заказа
    order = db.get_order(order_id)
    if not order:
        logger.warning(f"Order {order_id} not found")
        return
    
    # Проверяем наличие исполнителя
    performer_id = order.get('performer_id')
    if not performer_id:
        logger.warning(f"No performer for order {order_id}")
        return
    
    # Получаем сервис календаря
    service = get_calendar_service(performer_id)
    if not service:
        logger.warning(f"Calendar service unavailable for performer {performer_id}")
        return
    
    # Форматируем дату и время
    date_str = f"{order['order_date']} {order['order_time']}"
    
    # Валидация формата даты
    if not validate_date_time_format(date_str, "%d.%m.%Y %H:%M"):
        logger.error(f"Invalid date format for order {order_id}: {date_str}")
        return
    
    try:
        # Парсинг даты
        start_dt = datetime.strptime(date_str, "%d.%m.%Y %H:%M")
        start_iso = start_dt.isoformat()
        end_iso = (start_dt + timedelta(hours=2)).isoformat()
        
        # Формируем событие
        event = {
            'summary': f"Заказ #{order_id}",
            'description': (
                f"Программа: {order['order_program']}\n"
                f"Место: {order['order_location']}\n"
                f"Клиент: {order['user_name']}"
            ),
            'start': {
                'dateTime': start_iso,
                'timeZone': 'Europe/Moscow'
            },
            'end': {
                'dateTime': end_iso,
                'timeZone': 'Europe/Moscow'
            },
            'reminders': {
                'useDefault': True
            },
        }
        
        # Асинхронный вызов Google API
        loop = asyncio.get_running_loop()
        with ThreadPoolExecutor() as pool:
            created_event = await loop.run_in_executor(
                pool, 
                lambda: service.events().insert(
                    calendarId='primary',
                    body=event
                ).execute()
            )
        
        logger.info(f"Google Calendar event created: {created_event['id']}")
        
        # Обновляем заказ в БД
        with db.session_scope() as session:
            order_obj = session.query(Order).get(order_id)
            if order_obj:
                order_obj.calendar_event_id = created_event['id']
                session.commit()
                logger.debug(f"Order {order_id} updated with event ID")
    
    except HttpError as e:
        # Обработка ошибок авторизации
        if e.resp.status == 401:
            logger.error("Google API authorization expired. Clearing tokens...")
            try:
                with db.session_scope() as session:
                    performer_obj = session.query(Performer).filter_by(id=performer_id).first()
                    if performer_obj:
                        performer_obj.google_tokens = None
                        session.commit()
                        logger.info(f"Google tokens cleared for performer {performer_id}")
                        
                        # Очищаем кэш
                        if performer_id in SERVICE_CACHE:
                            del SERVICE_CACHE[performer_id]
            except Exception as db_error:
                logger.error(f"Error clearing tokens: {db_error}")
        
        else:
            logger.error(f"Google API error: {e}")
    
    except Exception as e:
        logger.error(f"Error syncing to Google Calendar: {e}", exc_info=True)