"""Estilos y componentes visuales para el dashboard (claro / oscuro)."""

from __future__ import annotations

import streamlit as st

STATUS_STYLE = {
    "Con capacidad": ("#059669", "#d1fae5", "🟢"),
    "Ocupado": ("#b45309", "#fef3c7", "🟡"),
    "A full": ("#c2410c", "#ffedd5", "🟠"),
    "Sobrecargado": ("#dc2626", "#fee2e2", "🔴"),
}

# Paletas por tema
THEMES = {
    "Claro": {
        "bg": "#f7f8fc",
        "surface": "#ffffff",
        "border": "#eef0f6",
        "text": "#1f2937",
        "muted": "#6b7280",
        "faint": "#9ca3af",
        "grid": "#eef0f6",
        "shadow": "rgba(17,24,39,.06)",
        "header_grad": "linear-gradient(120deg, #4f46e5 0%, #7c3aed 100%)",
    },
    "Oscuro": {
        "bg": "#0f172a",
        "surface": "#1e293b",
        "border": "#334155",
        "text": "#e2e8f0",
        "muted": "#94a3b8",
        "faint": "#64748b",
        "grid": "#334155",
        "shadow": "rgba(0,0,0,.35)",
        "header_grad": "linear-gradient(120deg, #6366f1 0%, #8b5cf6 100%)",
    },
}


def get_theme() -> dict:
    """Devuelve la paleta del tema seleccionado (guardado en sesion)."""
    name = st.session_state.get("theme", "Claro")
    return THEMES.get(name, THEMES["Claro"])


def status_badge_style(status: str) -> tuple[str, str]:
    """Color de texto y fondo del badge, adaptado al tema."""
    color, bg, _ = STATUS_STYLE.get(status, ("#374151", "#f3f4f6", "⚪"))
    if st.session_state.get("theme") == "Oscuro":
        # En oscuro usamos el color como texto y un fondo tenue
        return color, "rgba(255,255,255,.08)"
    return color, bg


def inject_css() -> None:
    """Inyecta el CSS global segun el tema activo."""
    t = get_theme()
    st.markdown(
        f"""
        <style>
        .stApp {{ background: {t['bg']} !important; }}
        div[data-testid="stAppViewContainer"] {{ background: {t['bg']} !important; }}
        div[data-testid="stMain"] {{ background: {t['bg']} !important; }}
        .block-container {{ padding-top: 1.5rem; padding-bottom: 3rem; max-width: 1300px; }}

        /* Textos generales al color del tema */
        .stApp, .stMarkdown, p, span, label, h1, h2, h3, h4, h5, h6 {{ color: {t['text']}; }}

        /* Header con gradiente */
        .app-header {{
            background: {t['header_grad']};
            border-radius: 16px; padding: 22px 28px; color: #fff;
            margin-bottom: 22px; box-shadow: 0 10px 30px rgba(79,70,229,.25);
        }}
        .app-header h1 {{ color:#fff !important; font-size:1.6rem; margin:0; font-weight:700; }}
        .app-header p {{ color:#e0e7ff !important; margin:6px 0 0; font-size:.9rem; }}

        /* Tarjetas KPI */
        .kpi-card {{
            background:{t['surface']}; border-radius:14px; padding:18px 20px;
            box-shadow: 0 4px 14px {t['shadow']};
            border: 1px solid {t['border']}; height:100%;
        }}
        .kpi-label {{ color:{t['muted']}; font-size:.78rem; text-transform:uppercase;
            letter-spacing:.04em; font-weight:600; margin-bottom:6px; }}
        .kpi-value {{ color:{t['text']}; font-size:1.7rem; font-weight:700; line-height:1; }}
        .kpi-sub {{ color:{t['faint']}; font-size:.75rem; margin-top:6px; }}

        .status-badge {{
            display:inline-block; padding:4px 12px; border-radius:999px;
            font-size:.8rem; font-weight:600;
        }}

        /* Botones */
        .stButton > button {{
            border-radius:10px; border:1px solid {t['border']}; font-weight:600;
            background:{t['surface']}; color:{t['text']}; transition: all .15s ease;
        }}
        .stButton > button:hover {{
            border-color:#6366f1; color:#818cf8;
            transform: translateY(-1px); box-shadow: 0 4px 12px rgba(99,102,241,.2);
        }}

        .stTabs [data-baseweb="tab-list"] {{ gap:6px; }}
        .stTabs [data-baseweb="tab"] {{ border-radius:10px 10px 0 0; padding:8px 16px; }}

        hr {{ margin:1.2rem 0; border-color:{t['border']}; }}

        section[data-testid="stSidebar"] {{
            background:{t['surface']}; border-right:1px solid {t['border']};
        }}

        /* Dataframes y widgets en oscuro */
        div[data-testid="stDataFrame"] {{ background:{t['surface']}; border-radius:10px; }}

        /* Ocultar barra superior de Streamlit (Deploy, menu, footer) */
        header[data-testid="stHeader"] {{ display: none !important; }}
        div[data-testid="stToolbar"] {{ display: none !important; }}
        div[data-testid="stToolbarActions"] {{ display: none !important; }}
        div[data-testid="stDecoration"] {{ display: none !important; }}
        [data-testid="stAppDeployButton"] {{ display: none !important; }}
        .stDeployButton {{ display: none !important; }}
        #MainMenu {{ display: none !important; }}
        footer {{ display: none !important; }}
        a[href*="streamlit.io"] {{ display: none !important; }}
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
    sub_html = f'<div class="kpi-sub">{sub}</div>' if sub else ""
    return f"""
        <div class="kpi-card" style="border-top:3px solid {accent}">
            <div class="kpi-label">{label}</div>
            <div class="kpi-value">{value}</div>
            {sub_html}
        </div>
    """


def kpi_row(cards: list[str]) -> None:
    cols = st.columns(len(cards))
    for col, html in zip(cols, cards):
        col.markdown(html, unsafe_allow_html=True)


def status_badge(status: str) -> str:
    color, bg = status_badge_style(status)
    return f'<span class="status-badge" style="color:{color};background:{bg}">{status}</span>'


def plotly_theme(fig):
    """Aplica fondo transparente y colores del tema a una figura Plotly."""
    t = get_theme()
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="sans-serif", color=t["text"]),
        legend=dict(font=dict(color=t["text"])),
    )
    fig.update_xaxes(gridcolor=t["grid"], zerolinecolor=t["grid"])
    fig.update_yaxes(gridcolor=t["grid"], zerolinecolor=t["grid"])
    return fig
