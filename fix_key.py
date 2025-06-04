# Создай файл fix_key.py
from cryptography.fernet import Fernet
import base64

def main():
    # Генерация правильного ключа
    key = Fernet.generate_key()
    key_str = key.decode('utf-8')
    
    print("=" * 60)
    print("🆕 НОВЫЙ КОРРЕКТНЫЙ КЛЮЧ ШИФРОВАНИЯ")
    print("=" * 60)
    print(key_str)
    print("=" * 60)
    print("1. Скопируйте этот ключ")
    print("2. Обновите .env файл: ENCRYPTION_KEY=новый_ключ")
    print("3. Удалите старый ключ из системы")
    print("=" * 60)

if __name__ == "__main__":
    main()