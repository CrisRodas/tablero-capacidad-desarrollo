"""Dashboard de capacidad de desarrolladores basado en ClickUp.

Lee directamente de la vista de Workload (Carga de trabajo) del espacio
Plataformas Alternas, calculando la capacidad por persona igual que ClickUp.
"""

from __future__ import annotations

import io
import os
from datetime import date, datetime, timedelta

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from dotenv import load_dotenv

from auth import require_login
from clickup_client import ClickUpClient, ClickUpError
from data_processing import (
    add_parent_names,
    build_capacity_summary,
    is_active_status,
    tasks_to_df,
)
from ui import header, inject_css, kpi_card, kpi_row, status_badge

load_dotenv()

st.set_page_config(
    page_title="Capacidad Plataformas Alternas",
    page_icon="📊",
    layout="wide",
)

inject_css()

# Bloquea el acceso hasta autenticar (fail-closed)
require_login()

# Espacio Plataformas Alternas y vista de Workload
DEFAULT_SPACE_ID = "90170456028"
DEFAULT_VIEW_ID = "8cev2bd-55197"

# Estados vigentes a analizar (se ignoran resuelto/cancelado/bloqueado/etc.)
ALLOWED_STATUS_LIST = [
    "abierto", "en análisis", "asignado", "en desarrollo", "en pruebas qa",
    "en pruebas usuario", "resuelto sin go live", "aprobado-pendiente vo.bo",
]

# Personas del equipo segun la configuracion de la vista de Workload
TEAM_ASSIGNEE_IDS = {
    "78851631", "90689526", "78872016", "89318985", "89340572", "89340945",
    "67477868", "264607679", "89194454", "89349317", "89146189", "101196260",
}

STATUS_COLORS = {
    "Con capacidad": "#10b981",
    "Ocupado": "#f59e0b",
    "A full": "#f97316",
    "Sobrecargado": "#ef4444",
}


@st.cache_data(ttl=1800, show_spinner=False)
def load_raw_space_tasks(token: str, team_id: str, space_id: str, statuses: tuple[str, ...]):
    """Trae las tareas vigentes del espacio en paralelo (cacheadas 30 min).

    Filtra por estado en la API para descargar solo lo relevante.
    """
    client = ClickUpClient(token, team_id)
    return client.get_space_tasks(space_id, statuses=list(statuses), max_workers=8)


def to_excel_bytes(sheets: dict[str, pd.DataFrame]) -> bytes:
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        for name, df in sheets.items():
            df.to_excel(writer, sheet_name=name[:31], index=False)
    return buffer.getvalue()


def _color_occupancy(val: float) -> str:
    """Color de fondo para la celda de % ocupacion."""
    if val >= 100:
        return "background-color: #f8d7da; color: #842029"
    if val >= 85:
        return "background-color: #ffe5d0; color: #8a4b1a"
    if val >= 50:
        return "background-color: #fff3cd; color: #664d03"
    return "background-color: #d1e7dd; color: #0f5132"


def style_summary(df: pd.DataFrame):
    """Aplica formato condicional a la tabla resumen."""
    styler = df.style
    if "% Ocupacion" in df.columns:
        styler = styler.map(_color_occupancy, subset=["% Ocupacion"])
    fmt = {c: "{:.1f}" for c in df.columns if df[c].dtype.kind in "fi"}
    return styler.format(fmt)


def build_workload_chart(
    tasks_df: pd.DataFrame, summary: pd.DataFrame, capacity_hours: float
) -> go.Figure:
    """Grafico tipo Workload de ClickUp: barras por persona, segmentos por tarea.

    El color de cada barra depende del estado de carga de la persona; los
    segmentos son sus tareas individuales. Linea vertical = capacidad.
    """
    order = summary.sort_values("hours_scheduled")["developer"].tolist()
    status_by_dev = dict(zip(summary["developer"], summary["status"]))

    # Ordenar tareas por dev y por horas para apilarlas de mayor a menor
    df = tasks_df.copy()
    df["_status"] = df["developer"].map(status_by_dev)
    df = df.sort_values(["developer", "hours_scheduled"], ascending=[True, False])

    # Un trace por estado (eficiente) coloreado segun la carga de la persona
    fig = go.Figure()
    for status, color in STATUS_COLORS.items():
        sub = df[df["_status"] == status]
        if sub.empty:
            continue
        fig.add_trace(
            go.Bar(
                x=sub["hours_scheduled"],
                y=sub["developer"],
                orientation="h",
                marker_color=color,
                marker_line_color="white",
                marker_line_width=0.5,
                name=status,
                customdata=sub[["task_name", "hours_scheduled"]].values,
                hovertemplate="%{customdata[0]}<br>%{customdata[1]:.1f}h<extra></extra>",
            )
        )

    fig.add_vline(
        x=capacity_hours,
        line_dash="dash",
        line_color="red",
        annotation_text=f"Capacidad {capacity_hours:.0f}h",
        annotation_position="top",
    )
    fig.update_layout(
        barmode="stack",
        height=max(400, len(order) * 45),
        xaxis_title="Horas programadas en el periodo",
        yaxis=dict(categoryorder="array", categoryarray=order),
        margin=dict(l=10, r=10, t=20, b=10),
        bargap=0.3,
        legend_title="Estado",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="sans-serif", color="#1f2937"),
    )
    fig.update_xaxes(gridcolor="#eef0f6")
    return fig


def render_person_view(
    dev: str, summary: pd.DataFrame, tasks_df: pd.DataFrame, capacity_hours: float
) -> None:
    """Vista dedicada de una persona con estimado vs ejecutado y detalle."""
    row = summary[summary["developer"] == dev]
    if row.empty:
        st.warning("No hay datos para esta persona en el periodo.")
        return
    row = row.iloc[0]

    st.markdown(f"### 👤 {dev}")
    st.markdown(status_badge(row["status"]), unsafe_allow_html=True)
    st.write("")

    # KPIs principales en tarjetas
    desviacion = round(row["hours_executed"] - row["hours_scheduled"], 1)
    occ_accent = ("#dc2626" if row["occupancy_pct"] >= 100 else
                  "#c2410c" if row["occupancy_pct"] >= 85 else
                  "#b45309" if row["occupancy_pct"] >= 50 else "#059669")
    kpi_row([
        kpi_card("Estimado", f"{row['hours_scheduled']:.1f}h", "horas programadas", "#4f46e5"),
        kpi_card("Ejecutado", f"{row['hours_executed']:.1f}h", "horas registradas", "#0891b2"),
        kpi_card("Desviacion", f"{desviacion:+.1f}h", "ejecutado - estimado", "#7c3aed"),
        kpi_card("Ocupacion", f"{row['occupancy_pct']:.0f}%", "de su capacidad", occ_accent),
    ])
    st.write("")

    dev_tasks = (
        tasks_df[tasks_df["developer"] == dev]
        .sort_values("hours_scheduled", ascending=False)
        .reset_index(drop=True)
    )
    if dev_tasks.empty:
        st.info("Sin tareas en el periodo para esta persona.")
        return

    color = STATUS_COLORS.get(row["status"], "#3498db")

    # Grafico estimado vs ejecutado por tarea (top 12)
    st.subheader("Estimado vs Ejecutado por tarea")
    top = dev_tasks.head(12).iloc[::-1]
    labels = top["task_name"].str.slice(0, 40)
    fig = go.Figure()
    fig.add_trace(go.Bar(
        y=labels, x=top["hours_scheduled"], orientation="h",
        name="Estimado", marker_color="#5dade2",
    ))
    fig.add_trace(go.Bar(
        y=labels, x=top["hours_executed"], orientation="h",
        name="Ejecutado", marker_color="#e67e22",
    ))
    fig.update_layout(
        barmode="group",
        height=max(400, len(top) * 45),
        xaxis_title="Horas",
        margin=dict(l=10, r=10, t=20, b=10),
        legend=dict(orientation="h", y=1.05),
    )
    st.plotly_chart(fig, width="stretch")

    # Distribucion por lista/proyecto
    col_a, col_b = st.columns(2)
    with col_a:
        st.subheader("Carga por lista")
        by_list = (
            dev_tasks.groupby("list_name")["hours_scheduled"].sum()
            .sort_values(ascending=False).reset_index()
        )
        by_list = by_list[by_list["hours_scheduled"] > 0]
        if not by_list.empty:
            fig_pie = px.pie(
                by_list, names="list_name", values="hours_scheduled", hole=0.4,
            )
            fig_pie.update_layout(height=320, margin=dict(l=10, r=10, t=10, b=10))
            st.plotly_chart(fig_pie, width="stretch")
        else:
            st.caption("Sin horas estimadas por lista.")

    with col_b:
        st.subheader("Resumen")
        n_tasks = len(dev_tasks)
        if "status_type" in dev_tasks.columns:
            n_activas = int(dev_tasks["status_type"].apply(is_active_status).sum())
        else:
            n_activas = n_tasks
        avance = (row["hours_executed"] / row["hours_scheduled"] * 100
                  if row["hours_scheduled"] else 0)
        st.metric("Tareas asignadas", n_tasks)
        st.metric("Tareas activas", n_activas)
        st.metric("Avance (ejec/estim)", f"{avance:.0f}%")
        libre = row["capacity_hours"] - row["hours_scheduled"]
        st.metric("Horas libres en el periodo", f"{libre:.1f}")

    # Tabla de tareas con desviacion
    st.subheader("Detalle de tareas")
    detalle = dev_tasks.copy()
    detalle["desviacion"] = (detalle["hours_executed"] - detalle["hours_scheduled"]).round(1)
    parent_col = ["parent_task"] if "parent_task" in detalle.columns else []
    detalle_disp = detalle[
        ["task_name", *parent_col, "list_name",
         "hours_scheduled", "hours_executed", "desviacion", "status"]
    ].rename(columns={
        "task_name": "Tarea / Subtarea",
        "parent_task": "Tarea padre",
        "list_name": "Lista",
        "hours_scheduled": "Estimado (h)",
        "hours_executed": "Ejecutado (h)",
        "desviacion": "Desviacion (h)",
        "status": "Estado",
    })
    st.dataframe(detalle_disp, width="stretch", hide_index=True)

    # Exportacion individual de la persona
    resumen_persona = pd.DataFrame([{
        "Desarrollador": dev,
        "Estimado (h)": row["hours_scheduled"],
        "Ejecutado (h)": row["hours_executed"],
        "Capacidad (h)": row["capacity_hours"],
        "% Ocupacion": row["occupancy_pct"],
        "Estado": row["status"],
    }])
    xls = to_excel_bytes({"Resumen": resumen_persona, "Tareas": detalle_disp})
    st.download_button(
        f"Descargar Excel de {dev}",
        data=xls,
        file_name=f"capacidad_{dev.replace(' ', '_')}_{datetime.now():%Y%m%d}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key="export_persona",
    )


# ---------------- Sidebar / configuracion ----------------

st.sidebar.title("Configuracion")

# Credenciales y vista tomadas del .env (no se muestran en la interfaz)
token = os.getenv("CLICKUP_API_TOKEN", "")
team_id = os.getenv("CLICKUP_TEAM_ID", "")
space_id = os.getenv("CLICKUP_SPACE_ID", DEFAULT_SPACE_ID)
capacity = st.sidebar.number_input(
    "Capacidad (horas/semana por dev)",
    min_value=1.0,
    value=float(os.getenv("CAPACITY_HOURS_PER_WEEK", "40")),
    step=1.0,
)
st.sidebar.markdown("### Periodo a analizar")
today = date.today()
preset = st.sidebar.radio(
    "Rango rapido",
    ["Esta semana", "Este mes", "Este trimestre", "Personalizado"],
    index=0,
)

_week_start = today - timedelta(days=today.weekday())
if preset == "Esta semana":
    default_start, default_end = _week_start, _week_start + timedelta(days=6)
elif preset == "Este mes":
    default_start = today.replace(day=1)
    _nm = (default_start.replace(day=28) + timedelta(days=4)).replace(day=1)
    default_end = _nm - timedelta(days=1)
elif preset == "Este trimestre":
    q_start_month = 3 * ((today.month - 1) // 3) + 1
    default_start = today.replace(month=q_start_month, day=1)
    _qm = default_start.month + 3
    _y = default_start.year + (1 if _qm > 12 else 0)
    _qm = _qm - 12 if _qm > 12 else _qm
    default_end = date(_y, _qm, 1) - timedelta(days=1)
else:
    default_start = _week_start
    default_end = _week_start + timedelta(days=6)

if preset == "Personalizado":
    c1, c2 = st.sidebar.columns(2)
    period_start = c1.date_input("Desde", value=default_start)
    period_end = c2.date_input("Hasta", value=default_end)
else:
    period_start, period_end = default_start, default_end
    st.sidebar.caption(f"{period_start:%d/%m/%Y} → {period_end:%d/%m/%Y}")

only_team = st.sidebar.checkbox(
    "Solo equipo de la vista (12 personas)", value=True,
    help="Filtra a los asignados configurados en la vista de Workload.",
)

if st.sidebar.button("Actualizar datos"):
    st.cache_data.clear()

header(
    "Tablero de Capacidad · Plataformas Alternas",
    f"Gestion de capacidad del equipo de desarrollo · Datos al {datetime.now():%d/%m/%Y %H:%M}",
)

if not token or not team_id or not space_id:
    st.info("Configura API Token, Team ID y Space ID en el .env para comenzar.")
    st.stop()

view_name = "Plataformas Alternas"
st.caption(
    f"Fuente: espacio '{view_name}' (estados vigentes) | Periodo: {period_start:%d/%m/%Y} - {period_end:%d/%m/%Y} "
    "| Horas distribuidas por rango de fechas (como el Workload de ClickUp)"
)

# ---------------- Carga de datos ----------------

try:
    with st.spinner("Cargando datos de ClickUp..."):
        raw_tasks = load_raw_space_tasks(
            token, team_id, space_id, tuple(ALLOWED_STATUS_LIST)
        )
except ClickUpError as e:
    st.error(f"No se pudo conectar con ClickUp: {e}")
    st.stop()

tasks_df = tasks_to_df(
    raw_tasks,
    period_start=period_start,
    period_end=period_end,
    team_assignee_ids=TEAM_ASSIGNEE_IDS if only_team else None,
)

# Resolver el nombre de la tarea padre de cada subtarea
_client = ClickUpClient(token, team_id)
tasks_df = add_parent_names(
    tasks_df, raw_tasks, name_resolver=_client.get_task_names
)

# Capacidad proporcional a los dias laborales del periodo
num_workdays = sum(
    1 for i in range((period_end - period_start).days + 1)
    if (period_start + timedelta(days=i)).weekday() < 5
)
num_weeks = max(num_workdays / 5, 0.2)

# Primer calculo con capacidad default para obtener la lista de personas
base_summary = build_capacity_summary(tasks_df, capacity, num_weeks)

if base_summary.empty:
    st.warning("No hay tareas con horas en la vista seleccionada.")
    st.stop()

# ----- Capacidad individual por persona (part-time, etc.) -----
if "cap_overrides" not in st.session_state:
    st.session_state.cap_overrides = {}

with st.sidebar.expander("Capacidad por persona (opcional)"):
    st.caption("Ajusta las horas/semana de quien no trabaje a tiempo completo.")
    editor_df = pd.DataFrame({
        "Desarrollador": base_summary["developer"],
        "Horas/semana": [
            st.session_state.cap_overrides.get(d, capacity)
            for d in base_summary["developer"]
        ],
    })
    edited = st.data_editor(
        editor_df, hide_index=True, width="stretch", key="cap_editor",
        column_config={
            "Desarrollador": st.column_config.TextColumn(disabled=True),
            "Horas/semana": st.column_config.NumberColumn(min_value=0, step=1),
        },
    )
    # Guardar solo los que difieren del default
    st.session_state.cap_overrides = {
        r["Desarrollador"]: r["Horas/semana"]
        for _, r in edited.iterrows()
        if r["Horas/semana"] != capacity
    }

summary = build_capacity_summary(
    tasks_df, capacity, num_weeks, st.session_state.cap_overrides
)

capacity_hours = capacity * num_weeks

# Estado de navegacion (persona seleccionada)
if "selected_dev" not in st.session_state:
    st.session_state.selected_dev = None

# ================= VISTA DE PERSONA =================
if st.session_state.selected_dev:
    if st.button("← Volver a la vista general"):
        st.session_state.selected_dev = None
        st.rerun()

    render_person_view(
        st.session_state.selected_dev, summary, tasks_df, capacity_hours
    )

# ================= VISTA GENERAL =================
else:
    # ----- Resumen ejecutivo -----
    n_devs = len(summary)
    total_cap = summary["capacity_hours"].sum()
    total_prog = summary["hours_scheduled"].sum()
    horas_libres = round(max(total_cap - total_prog, 0), 1)
    ocup_prom = round(total_prog / total_cap * 100, 1) if total_cap else 0
    total_exec = summary["hours_executed"].sum()
    # Precision de estimacion a nivel equipo
    desv_pct = (
        round((total_exec - total_prog) / total_prog * 100, 1) if total_prog else 0
    )

    st.markdown("#### Resumen ejecutivo")
    ocup_accent = ("#dc2626" if ocup_prom >= 100 else
                   "#c2410c" if ocup_prom >= 85 else
                   "#b45309" if ocup_prom >= 50 else "#059669")
    kpi_row([
        kpi_card("Equipo", str(n_devs), "desarrolladores", "#4f46e5"),
        kpi_card("Ocupacion promedio", f"{ocup_prom:.0f}%",
                 "carga vs capacidad", ocup_accent),
        kpi_card("Horas libres", f"{horas_libres:.0f}",
                 "disponibles en el periodo", "#0891b2"),
        kpi_card("Con capacidad",
                 str(int((summary["status"] == "Con capacidad").sum())),
                 "personas con holgura", "#059669"),
        kpi_card("Desviacion estimacion", f"{desv_pct:+.0f}%",
                 "ejecutado vs estimado", "#7c3aed"),
    ])
    st.write("")

    # ----- Panel de alertas / semaforo -----
    sobrecargados = summary[summary["status"] == "Sobrecargado"]
    subutilizados = summary[summary["status"] == "Con capacidad"]
    ca, cb = st.columns(2)
    with ca:
        if not sobrecargados.empty:
            st.error(f"⚠ {len(sobrecargados)} persona(s) sobrecargada(s)")
            for _, r in sobrecargados.head(5).iterrows():
                exceso = r["hours_scheduled"] - r["capacity_hours"]
                st.caption(f"• {r['developer']}: {r['occupancy_pct']:.0f}% "
                           f"(+{exceso:.0f}h sobre capacidad)")
        else:
            st.success("Sin personas sobrecargadas")
    with cb:
        if not subutilizados.empty:
            st.info(f"✓ {len(subutilizados)} persona(s) con capacidad disponible")
            for _, r in subutilizados.head(5).iterrows():
                st.caption(f"• {r['developer']}: puede recibir "
                           f"~{r['available_hours']:.0f}h mas")
        else:
            st.caption("Nadie con holgura significativa.")

    st.divider()

    st.subheader("Carga de trabajo por desarrollador")
    st.caption(
        f"Linea roja = capacidad del periodo ({capacity_hours:.0f}h). "
        f"Puedes hacer click en una barra o usar los botones de abajo."
    )
    fig = build_workload_chart(tasks_df, summary, capacity_hours)
    event = st.plotly_chart(
        fig, width="stretch", on_select="rerun", key="workload_chart"
    )

    # Capturar click en una barra -> abrir vista de esa persona
    points = (event.get("selection", {}) or {}).get("points", []) if event else []
    if points:
        clicked_dev = points[0].get("y")
        if clicked_dev:
            st.session_state.selected_dev = clicked_dev
            st.rerun()

    # Botones por persona: click en el nombre abre su detalle
    st.markdown("##### Ver detalle por persona (haz click en un nombre)")
    ordered = summary.sort_values("occupancy_pct", ascending=False)
    cols = st.columns(3)
    for i, (_, r) in enumerate(ordered.iterrows()):
        icono = {
            "Sobrecargado": "🔴", "A full": "🟠",
            "Ocupado": "🟡", "Con capacidad": "🟢",
        }.get(r["status"], "⚪")
        label = f"{icono} {r['developer']}  ·  {r['occupancy_pct']:.0f}%"
        if cols[i % 3].button(label, key=f"dev_btn_{r['developer']}", width="stretch"):
            st.session_state.selected_dev = r["developer"]
            st.rerun()

    st.divider()
    st.subheader("Detalle de capacidad")
    summary_disp = summary.rename(
        columns={
            "developer": "Desarrollador",
            "hours_scheduled": "Horas programadas",
            "hours_executed": "Horas ejecutadas",
            "capacity_hours": "Capacidad (h)",
            "occupancy_pct": "% Ocupacion",
            "available_hours": "Horas disponibles",
            "status": "Estado",
        }
    )
    st.dataframe(
        style_summary(summary_disp),
        width="stretch",
        hide_index=True,
    )

    # ----- Exportacion -----
    st.divider()
    st.subheader("Exportar tablero")
    sheets = {"Resumen_Capacidad": summary, "Detalle_Tareas": tasks_df}
    excel_bytes = to_excel_bytes(sheets)

    c1, c2 = st.columns(2)
    c1.download_button(
        "Descargar Excel",
        data=excel_bytes,
        file_name=f"capacidad_plataformas_{datetime.now():%Y%m%d}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    c2.download_button(
        "Descargar CSV (resumen)",
        data=summary.to_csv(index=False).encode("utf-8"),
        file_name=f"capacidad_resumen_{datetime.now():%Y%m%d}.csv",
        mime="text/csv",
    )

# ---------------- Footer ----------------
st.divider()
st.caption(
    f"Fuente: ClickUp · vista '{view_name}' | Periodo "
    f"{period_start:%d/%m/%Y}–{period_end:%d/%m/%Y} | "
    f"Generado {datetime.now():%d/%m/%Y %H:%M}"
)
