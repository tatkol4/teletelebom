import os
import logging
import shutil
import json
from contextlib import contextmanager
from datetime import datetime
from typing import Dict, Optional, List
from cachetools import TTLCache
from sqlalchemy import create_engine, Index
from sqlalchemy.orm import sessionmaker, scoped_session
from sqlalchemy.pool import QueuePool
from sqlalchemy import inspect  # Ключевой импорт для работы с метаданными БД
from sqlalchemy import text  # Добавляем импорт

from .base import Base
from .config import config
from models.order import Order
from models.performer import Performer
from models.support_ticket import SupportTicket

logger = logging.getLogger(__name__)

class Database:
    def __init__(self, db_url: str = f"sqlite:///{config.DATABASE_NAME}"):
        self.engine = create_engine(
            db_url, 
            poolclass=QueuePool,
            pool_size=10,
            max_overflow=5,
            pool_timeout=30
        )
        self.Session = scoped_session(sessionmaker(bind=self.engine))
        
        # Создаем таблицы, если их нет
        Base.metadata.create_all(self.engine)
        
        # Применяем миграции
        self._apply_migrations()
        
        # Создаем кэши
        self.order_cache = TTLCache(maxsize=500, ttl=1800)
        self.performer_cache = TTLCache(maxsize=100, ttl=3600)
        self.availability_cache = TTLCache(maxsize=1000, ttl=300)
    
    def _apply_migrations(self):
        """Применяем необходимые миграции для существующих таблиц"""
        # Проверяем только существующие таблицы
        if not self._table_exists("support_tickets"):
            logger.info("Table 'support_tickets' doesn't exist, skipping migrations")
            return
        
        # Применяем миграции внутри транзакции
        with self.session_scope() as session:
            try:
                logger.info("Checking for database migrations...")
                
                # Для таблицы support_tickets
                if not self._column_exists("support_tickets", "user_name"):
                    logger.info("Adding column 'user_name' to support_tickets")
                    session.execute(text("ALTER TABLE support_tickets ADD COLUMN user_name TEXT"))
                
                if not self._column_exists("support_tickets", "username"):
                    logger.info("Adding column 'username' to support_tickets")
                    session.execute(text("ALTER TABLE support_tickets ADD COLUMN username TEXT"))
                
                if not self._column_exists("support_tickets", "photo_path"):
                    logger.info("Adding column 'photo_path' to support_tickets")
                    session.execute(text("ALTER TABLE support_tickets ADD COLUMN photo_path TEXT"))
                
                session.commit()
                logger.info("Database migrations applied successfully")
            except Exception as e:
                logger.error(f"Migration failed: {e}", exc_info=True)
                session.rollback()
                # Для SQLite не требуется пробрасывать исключение дальше
                if "sqlite" not in self.engine.url.drivername:
                    raise
    
    def _table_exists(self, table_name: str) -> bool:
        """Проверяет существование таблицы в базе данных"""
        return inspect(self.engine).has_table(table_name)
    
    def _column_exists(self, table_name: str, column_name: str) -> bool:
        """Проверяет существование столбца в таблице"""
        if not self._table_exists(table_name):
            return False
            
        inspector = inspect(self.engine)
        columns = [col['name'] for col in inspector.get_columns(table_name)]
        return column_name in columns
    
    @contextmanager
    def session_scope(self):
        session = self.Session()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Database error: {e}", exc_info=True)
            raise
        finally:
            session.close()
    
    # ... остальные методы без изменений ...

    
    def save_order(self, order_data: dict) -> int:
        with self.session_scope() as session:
            order = Order(**order_data)
            session.add(order)
            session.flush()
            return order.id
    
    def get_order(self, order_id: int) -> Optional[Dict]:
        # Используем локальный кэш вместо Redis
        cache_key = order_id
        if cache_key in self.order_cache:
            return self.order_cache[cache_key]
        
        with self.session_scope() as session:
            order = session.query(Order).get(order_id)
            if order:
                result = {c.name: getattr(order, c.name) for c in order.__table__.columns}
                self.order_cache[cache_key] = result
                return result
        return None
    
    def update_order_status(self, order_id: int, status: str):
        with self.session_scope() as session:
            order = session.query(Order).get(order_id)
            if order:
                order.status = status
                # Удаляем из кэша
                cache_key = order_id
                if cache_key in self.order_cache:
                    del self.order_cache[cache_key]
    
    def get_performer(self, name: str) -> Optional[Dict]:
        cache_key = name
        if cache_key in self.performer_cache:
            return self.performer_cache[cache_key]
        
        with self.session_scope() as session:
            performer = session.query(Performer).filter_by(performer_name=name).first()
            if performer:
                result = {c.name: getattr(performer, c.name) for c in performer.__table__.columns}
                self.performer_cache[cache_key] = result
                return result
        return None
    
    def is_performer_available(self, performer_name: str, date: str, time: str) -> bool:
        cache_key = (performer_name, date, time)
        if cache_key in self.availability_cache:
            return self.availability_cache[cache_key]
        
        with self.session_scope() as session:
            count = session.query(Order).filter(
                Order.order_performers == performer_name,
                Order.order_date == date,
                Order.order_time == time,
                Order.status.in_(["pending", "confirmed"])
            ).count()
            is_available = count == 0
            self.availability_cache[cache_key] = is_available
            return is_available
    
    def create_support_ticket(self, user_id: int, message: str, user_name: str = None, username: str = None) -> int:
        """
    Создает запрос в поддержку с возможностью указания дополнительной информации
         """
        with self.session_scope() as session:
            # Если имя не указано, попробуем получить из профиля исполнителя
            if not user_name:
                performer = session.query(Performer).filter_by(telegram_user_id=user_id).first()
                if performer:
                    user_name = performer.performer_name
                    username = performer.telegram_user_id
        
        # Создаем объект
        ticket = SupportTicket(
            user_id=user_id,
            message=message,
            user_name=user_name or f"User_{user_id}",
            username=username or f"user_{user_id}"
        )
        session.add(ticket)
        session.flush()
        return ticket.id

def get_support_ticket(self, ticket_id: int) -> Optional[Dict]:
    """
    Получает информацию о тикете поддержки
    """
    with self.session_scope() as session:
        ticket = session.query(SupportTicket).get(ticket_id)
        if ticket:
            return {
                "id": ticket.id,
                "user_id": ticket.user_id,
                "user_name": ticket.user_name,
                "username": ticket.username,
                "message": ticket.message,
                "created_at": ticket.created_at,
                "resolved": ticket.resolved,
                "photo_path": ticket.photo_path
            }
    return None
    
    def create_backup(self) -> str:
        os.makedirs(config.BACKUP_DIR, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = os.path.join(config.BACKUP_DIR, f"{config.DATABASE_NAME}.bak_{timestamp}")
        shutil.copy2(config.DATABASE_NAME, backup_path)
        return backup_path
    
    def get_performer_by_user_id(self, user_id: int) -> Optional[Dict]:
        """Поиск исполнителя по Telegram user_id"""
        with self.session_scope() as session:
            performer = session.query(Performer).filter_by(telegram_user_id=user_id).first()
            if performer:
                return {c.name: getattr(performer, c.name) for c in performer.__table__.columns}
        return None

db = Database()