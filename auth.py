"""Autenticacion simple por contrasena para el dashboard.

La contrasena NO se guarda en el codigo: se lee de la variable de entorno
APP_PASSWORD (texto) o APP_PASSWORD_SHA256 (hash sha256, preferido).
"""

from __future__ import annotations

import hashlib
import hmac

import streamlit as st

from config import get_setting


def _password_ok(entered: str) -> bool:
    """Compara la contrasena ingresada de forma segura (timing-safe)."""
    hashed = get_setting("APP_PASSWORD_SHA256", "").strip().lower()
    if hashed:
        digest = hashlib.sha256(entered.encode("utf-8")).hexdigest()
        return hmac.compare_digest(digest, hashed)

    plain = get_setting("APP_PASSWORD", "")
    if plain:
        return hmac.compare_digest(entered, plain)

    return False


def require_login() -> None:
    """Bloquea la app hasta que se ingrese la contrasena correcta.

    Si no hay contrasena configurada, muestra un aviso y detiene la app
    (fail-closed: no se expone data sin proteccion).
    """
    if not get_setting("APP_PASSWORD_SHA256") and not get_setting("APP_PASSWORD"):
        st.error(
            "Acceso no configurado. Define APP_PASSWORD_SHA256 (o APP_PASSWORD) "
            "en el entorno antes de usar el tablero."
        )
        st.stop()

    if st.session_state.get("_authenticated"):
        return

    st.markdown("### 🔒 Acceso restringido")
    st.caption("Tablero interno - Plataformas Alternas")
    pwd = st.text_input("Contrasena", type="password")
    col1, _ = st.columns([1, 3])
    if col1.button("Ingresar"):
        if _password_ok(pwd):
            st.session_state["_authenticated"] = True
            st.rerun()
        else:
            st.error("Contrasena incorrecta.")
    st.stop()
