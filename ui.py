"""Estilos y componentes visuales para el dashboard."""

from __future__ import annotations

import streamlit as st

STATUS_STYLE = {
    "Con capacidad": ("#059669", "#d1fae5", "🟢"),
    "Ocupado": ("#b45309", "#fef3c7", "🟡"),
    "A full": ("#c2410c", "#ffedd5", "🟠"),
    "Sobrecargado": ("#dc2626", "#fee2e2", "🔴"),
}


def inject_css() -> None:
    """Inyecta el CSS global del dashboard."""
    st.markdown(
        """
        <style>
        /* Contenedor principal mas aireado */
        .block-container { padding-top: 2rem; padding-bottom: 3rem; max-width: 1300px; }

        /* Header con gradiente */
        .app-header {
            background: linear-gradient(120deg, #4f46e5 0%, #7c3aed 100%);
            border-radius: 16px;
            padding: 22px 28px;
            color: #fff;
            margin-bottom: 22px;
            box-shadow: 0 10px 30px rgba(79,70,229,.25);
        }
        .app-header h1 { color:#fff; font-size: 1.6rem; margin:0; font-weight:700; }
        .app-header p { color: #e0e7ff; margin: 6px 0 0; font-size:.9rem; }

        /* Tarjetas KPI */
        .kpi-card {
            background:#fff; border-radius:14px; padding:18px 20px;
            box-shadow: 0 4px 14px rgba(17,24,39,.06);
            border: 1px solid #eef0f6; height: 100%;
        }
        .kpi-label { color:#6b7280; font-size:.78rem; text-transform:uppercase;
            letter-spacing:.04em; font-weight:600; margin-bottom:6px; }
        .kpi-value { color:#111827; font-size:1.7rem; font-weight:700; line-height:1; }
        .kpi-sub { color:#9ca3af; font-size:.75rem; margin-top:6px; }

        /* Badge de estado */
        .status-badge {
            display:inline-block; padding:4px 12px; border-radius:999px;
            font-size:.8rem; font-weight:600;
        }

        /* Botones mas suaves */
        .stButton > button {
            border-radius:10px; border:1px solid #e5e7eb; font-weight:600;
            transition: all .15s ease;
        }
        .stButton > button:hover {
            border-color:#4f46e5; color:#4f46e5;
            transform: translateY(-1px);
            box-shadow: 0 4px 12px rgba(79,70,229,.15);
        }

        /* Tabs mas visibles */
        .stTabs [data-baseweb="tab-list"] { gap: 6px; }
        .stTabs [data-baseweb="tab"] {
            border-radius:10px 10px 0 0; padding: 8px 16px;
        }

        /* Divider mas sutil */
        hr { margin: 1.2rem 0; border-color:#eef0f6; }

        /* Sidebar */
        section[data-testid="stSidebar"] { background:#ffffff; border-right:1px solid #eef0f6; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def header(title: str, subtitle: str) -> None:
    st.markdown(
        f"""
        <div class="app-header">
            <h1>📊 {title}</h1>
            <p>{subtitle}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def kpi_card(label: str, value: str, sub: str = "", accent: str = "#4f46e5") -> str:
    """Devuelve el HTML de una tarjeta KPI."""
    sub_html = f'<div class="kpi-sub">{sub}</div>' if sub else ""
    return f"""
        <div class="kpi-card" style="border-top:3px solid {accent}">
            <div class="kpi-label">{label}</div>
            <div class="kpi-value">{value}</div>
            {sub_html}
        </div>
    """


def kpi_row(cards: list[str]) -> None:
    """Renderiza una fila de tarjetas KPI (lista de HTML de kpi_card)."""
    cols = st.columns(len(cards))
    for col, html in zip(cols, cards):
        col.markdown(html, unsafe_allow_html=True)


def status_badge(status: str) -> str:
    color, bg, _ = STATUS_STYLE.get(status, ("#374151", "#f3f4f6", "⚪"))
    return f'<span class="status-badge" style="color:{color};background:{bg}">{status}</span>'
