import logging
import os
import re
from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)

def _validate_key(key: str) -> bool:
    """Проверяет формат ключа шифрования"""
    if not key:
        return False
    if len(key) != 44:
        logger.error(f"Invalid key length: {len(key)} (expected 44)")
        return False
    
    # Разрешаем все символы из base64: A-Z, a-z, 0-9, +, /, = (но Fernet использует url-safe варианты)
    if not re.match(r'^[A-Za-z0-9_=-]{44}$', key):
        logger.error("Key contains invalid characters")
        return False
    return True

def create_cipher_suite():
    """Создает объект для шифрования/дешифровки"""
    key = os.getenv("ENCRYPTION_KEY")
    
    if not key:
        logger.critical("ENCRYPTION_KEY is not set in environment!")
        raise RuntimeError("Encryption key is missing")
    
    # Удаляем возможные пробелы и кавычки
    key = key.strip().strip('"').strip("'")
    
    if not _validate_key(key):
        logger.critical(f"Invalid ENCRYPTION_KEY format: {key}")
        raise ValueError("Fernet key must be 32 url-safe base64-encoded bytes")
    
    try:
        test_cipher = Fernet(key.encode())
        test_cipher.encrypt(b"test")
        return test_cipher
    except Exception as e:
        logger.critical(f"Key validation failed: {e}")
        raise

def encrypt_data(data: str) -> str:
    """Шифрует строку данных"""
    if not data:
        return ""
    
    cipher_suite = create_cipher_suite()
    try:
        return cipher_suite.encrypt(data.encode()).decode()
    except Exception as e:
        logger.error(f"Encryption failed: {e}")
        return ""

def decrypt_data(encrypted_data: str) -> str:
    """Дешифрует строку данных"""
    if not encrypted_data:
        return ""
    
    cipher_suite = create_cipher_suite()
    try:
        return cipher_suite.decrypt(encrypted_data.encode()).decode()
    except InvalidToken:
        logger.error("Decryption failed: invalid token")
        return ""
    except Exception as e:
        logger.error(f"Decryption error: {e}")
        return ""