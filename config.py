import os
import json
import logging
import re
from dotenv import load_dotenv
from typing import List, Dict, Any, Optional

load_dotenv()

logger = logging.getLogger(__name__)

class BotConfig:
    def __init__(self):
        self.BOT_TOKEN = os.getenv("BOT_TOKEN")
        if not self.BOT_TOKEN:
            raise ValueError("BOT_TOKEN is required in .env file")
        
        self.TARGET_CHAT_ID = os.getenv("TARGET_CHAT_ID")
        self.TARGET_TOPIC_ID = int(os.getenv("TARGET_TOPIC_ID", "45"))
        self.DATABASE_NAME = os.getenv("DATABASE_NAME", "orders.db")
        self.BACKUP_DIR = os.getenv("BACKUP_DIR", "backups")
        self.LOG_FILE = os.getenv("LOG_FILE", "bot.log")
        
        self.ADMIN_IDS = self._parse_int_list(os.getenv("ADMIN_IDS", ""))
        self.SUPPORT_OPERATORS = self._parse_int_list(os.getenv("SUPPORT_OPERATORS", ""))
        
        self.TWILIO_SID = os.getenv("TWILIO_SID")
        self.TWILIO_TOKEN = os.getenv("TWILIO_TOKEN")
        if not self.TWILIO_TOKEN:
            logger.warning("TWILIO_TOKEN is not set! SMS/WhatsApp notifications will be disabled")
        self.TWILIO_NUMBER = os.getenv("TWILIO_NUMBER")
        self.SMTP_SERVER = os.getenv("SMTP_SERVER")
        self.SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
        self.SMTP_USER = os.getenv("SMTP_USER")
        self.SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
        if not self.SMTP_PASSWORD:
            logger.warning("SMTP_PASSWORD is not set! Email notifications will be disabled")
        self.SMTP_FROM = os.getenv("SMTP_FROM")
        self.ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY")
        self._encrypt_sensitive()
        
        self.S3_BUCKET = os.getenv("S3_BUCKET")
        self.S3_REGION = os.getenv("S3_REGION", "us-east-1")
        self.AWS_ACCESS_KEY = os.getenv("AWS_ACCESS_KEY")
        self.AWS_SECRET_KEY = os.getenv("AWS_SECRET_KEY")
        self.S3_ENABLED = all([self.S3_BUCKET, self.AWS_ACCESS_KEY, self.AWS_SECRET_KEY])
        
        self.DATE_REGEX = r'^\d{2}\.\d{2}\.\d{4}$'
        self.TIME_REGEX = r'^\d{2}:\d{2}$'
        self.AMOUNT_REGEX = r'^\d+(\.\d{1,2})?$'
        self.CALENDAR_SELECT_DAY_PREFIX = "CSD"
        self.CALENDAR_PREV_MONTH_PREFIX = "CPM"
        self.CALENDAR_NEXT_MONTH_PREFIX = "CNM"
        self._validate_required_vars()
        self.refresh_data()
    
    def _validate_required_vars(self):
        """Проверяет наличие обязательных переменных"""
        required_vars = [
            'BOT_TOKEN', 'ENCRYPTION_KEY'
        ]
        
        for var in required_vars:
            if not getattr(self, var, None):
                logger.error(f"Critical: {var} is not set in .env file!")
                raise ValueError(f"{var} is required in .env file")
        
        # Для необязательных, но важных параметров
        if not self.SMTP_PASSWORD:
            logger.warning("SMTP_PASSWORD is not set. Email notifications will be disabled")
        
        if not self.TWILIO_TOKEN:
            logger.warning("TWILIO_TOKEN is not set. SMS/WhatsApp notifications will be disabled")

    def _encrypt_sensitive(self):
        """Шифрует чувствительные данные в памяти"""
        from core.security import encrypt_data
        
        if not self.ENCRYPTION_KEY:
            logger.warning("ENCRYPTION_KEY not set, skipping encryption")
            return
        
        if self.SMTP_PASSWORD and not self.SMTP_PASSWORD.startswith("gAAAA"):
            self.SMTP_PASSWORD = encrypt_data(self.SMTP_PASSWORD)
        
        if self.TWILIO_TOKEN and not self.TWILIO_TOKEN.startswith("gAAAA"):
            self.TWILIO_TOKEN = encrypt_data(self.TWILIO_TOKEN)

    def _parse_int_list(self, value: str) -> List[int]:
        if not value:
            return []
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return [int(x.strip()) for x in value.split(',') if x.strip().isdigit()]
    
    def refresh_data(self):
        self.PERFORMERS_LIST = ["Титов Андрей", "Шепелев Олег", "Любой свободный"]
        self.PROGRAM_CATEGORIES = [
            "Азотное шоу", "Тесла шоу", "Физическое шоу премиум", 
            "Механическое шоу стандартное", "Механическое шоу премиум", "Шоу трансформера"
        ]
        self.PROGRAM_SUB_CATEGORIES = {
            "Азотное шоу": [
                "Азотное шоу классическое", "Азотное шоу стандарт",
                "Азотное шоу премиум", "Азотное шоу VIP"
            ],
            "Тесла шоу": [
                "Тесла шоу классическое", "Тесла шоу стандарт", "Тесла шоу премиум"
            ]
        }
        self.TIME_SLOTS = [f"{h:02d}:{m:02d}" for h in range(9, 21) for m in (0, 30) if (h, m) != (20, 30)]

class States:
    (ASK_DATE, ASK_TIME, ASK_LOCATION, ASK_PERFORMERS, ASK_PROGRAM, ASK_PROGRAM_SUB, 
     ASK_AMOUNT, ASK_DETAILS, REVIEW_ORDER, PERFORMER_CONFIRMATION, PERFORMER_FEEDBACK,
     SUPPORT_REQUEST, SUPPORT_CONFIRM) = range(13)

config = BotConfig()
states = States()