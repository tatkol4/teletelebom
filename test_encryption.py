# test_encryption.py
from core.config import config
from core.security import encrypt_data, decrypt_data

def test_encryption():
    test_data = "SuperSecretPassword123"
    
    print("Original:", test_data)
    
    # Шифруем
    encrypted = encrypt_data(test_data)
    print("Encrypted:", encrypted)
    
    # Дешифруем
    decrypted = decrypt_data(encrypted)
    print("Decrypted:", decrypted)
    
    # Проверяем
    assert test_data == decrypted, "Encryption/decryption failed!"
    print("✅ Test passed!")

if __name__ == "__main__":
    test_encryption()