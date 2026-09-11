"""Lectura de configuracion compatible con .env local y Streamlit Cloud.

Prioridad: st.secrets (Streamlit Cloud) > variables de entorno (.env).
"""

from __future__ import annotations

import os


def get_setting(key: str, default: str = "") -> str:
    """Devuelve un valor de config buscando primero en st.secrets."""
    # st.secrets puede no existir fuera de Streamlit; se importa de forma segura
    try:
        import streamlit as st

        if key in st.secrets:
            return str(st.secrets[key])
    except Exception:
        pass
    return os.getenv(key, default)
