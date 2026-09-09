"""Genera el hash SHA-256 de una contrasena para APP_PASSWORD_SHA256.

Uso:
    python generar_password.py
Luego copia el hash en tu .env como APP_PASSWORD_SHA256=<hash>
"""

import getpass
import hashlib

if __name__ == "__main__":
    pwd = getpass.getpass("Nueva contrasena del tablero: ")
    pwd2 = getpass.getpass("Confirma la contrasena: ")
    if pwd != pwd2:
        print("Las contrasenas no coinciden.")
    elif len(pwd) < 8:
        print("Usa al menos 8 caracteres.")
    else:
        h = hashlib.sha256(pwd.encode("utf-8")).hexdigest()
        print("\nAgrega esta linea a tu .env:")
        print(f"APP_PASSWORD_SHA256={h}")
