# generate_key.py
from cryptography.fernet import Fernet

def main():
    # Генерация криптографического ключа
    key = Fernet.generate_key()
    
    # Преобразование в строку для удобства использования
    key_str = key.decode('utf-8')
    
    print("=" * 60)
    print("🔑 СГЕНЕРИРОВАН КЛЮЧ ШИФРОВАНИЯ")
    print("=" * 60)
    print(f"Ключ: {key_str}")
    print("=" * 60)
    print("ВАЖНЫЕ ИНСТРУКЦИИ:")
    print("1. Скопируйте ключ и добавьте его в .env файл:")
    print(f'   ENCRYPTION_KEY="{key_str}"')
    print("2. Никогда не коммитьте этот ключ в репозиторий!")
    print("3. Храните ключ в надежном месте (менеджер паролей)")
    print("=" * 60)

if __name__ == "__main__":
    main()