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
import streamlit as st
from dotenv import load_dotenv

from clickup_client import ClickUpClient, ClickUpError
from data_processing import build_capacity_summary, tasks_to_df

load_dotenv()

st.set_page_config(page_title="Capacidad Plataformas Alternas", layout="wide")

# Vista de Workload por defecto (espacio Plataformas Alternas)
DEFAULT_VIEW_ID = "8cev2bd-55197"

# Personas del equipo segun la configuracion de la vista de Workload
TEAM_ASSIGNEE_IDS = {
    "78851631", "90689526", "78872016", "89318985", "89340572", "89340945",
    "67477868", "264607679", "89194454", "89349317", "89146189", "101196260",
}

STATUS_COLORS = {
    "Con capacidad": "#2ecc71",
    "Ocupado": "#f1c40f",
    "A full": "#e67e22",
    "Sobrecargado": "#e74c3c",
}


@st.cache_data(ttl=300, show_spinner=False)
def load_raw_view_tasks(token: str, team_id: str, view_id: str):
    """Trae las tareas crudas de la vista (cacheadas)."""
    client = ClickUpClient(token, team_id)
    return list(client.iter_view_tasks(view_id))


@st.cache_data(ttl=600, show_spinner=False)
def load_view_name(token: str, team_id: str, view_id: str) -> str:
    client = ClickUpClient(token, team_id)
    try:
        return client.get_view(view_id).get("name", view_id)
    except ClickUpError:
        return view_id


def to_excel_bytes(sheets: dict[str, pd.DataFrame]) -> bytes:
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        for name, df in sheets.items():
            df.to_excel(writer, sheet_name=name[:31], index=False)
    return buffer.getvalue()


# ---------------- Sidebar / configuracion ----------------

st.sidebar.title("Configuracion")

# Credenciales y vista tomadas del .env (no se muestran en la interfaz)
token = os.getenv("CLICKUP_API_TOKEN", "")
team_id = os.getenv("CLICKUP_TEAM_ID", "")
view_id = os.getenv("CLICKUP_VIEW_ID", DEFAULT_VIEW_ID)
capacity = st.sidebar.number_input(
    "Capacidad (horas/semana por dev)",
    min_value=1.0,
    value=float(os.getenv("CAPACITY_HOURS_PER_WEEK", "40")),
    step=1.0,
)
st.sidebar.markdown("### Periodo a analizar")
today = date.today()
default_start = today - timedelta(days=today.weekday())  # lunes de esta semana
default_end = default_start + timedelta(days=6)  # domingo
c1, c2 = st.sidebar.columns(2)
period_start = c1.date_input("Desde", value=default_start)
period_end = c2.date_input("Hasta", value=default_end)

only_team = st.sidebar.checkbox(
    "Solo equipo de la vista (12 personas)", value=True,
    help="Filtra a los asignados configurados en la vista de Workload.",
)

if st.sidebar.button("Actualizar datos"):
    st.cache_data.clear()

st.title("Tablero de Capacidad - Plataformas Alternas")

if not token or not team_id or not view_id:
    st.info("Ingresa API Token, Team ID y View ID en la barra lateral para comenzar.")
    st.stop()

view_name = load_view_name(token, team_id, view_id)
st.caption(
    f"Fuente: vista '{view_name}' | Periodo: {period_start:%d/%m/%Y} - {period_end:%d/%m/%Y} "
    "| Horas distribuidas por rango de fechas (como el Workload de ClickUp)"
)

# ---------------- Carga de datos ----------------

try:
    with st.spinner("Cargando datos de ClickUp..."):
        raw_tasks = load_raw_view_tasks(token, team_id, view_id)
except ClickUpError as e:
    st.error(f"No se pudo conectar con ClickUp: {e}")
    st.stop()

tasks_df = tasks_to_df(
    raw_tasks,
    period_start=period_start,
    period_end=period_end,
    team_assignee_ids=TEAM_ASSIGNEE_IDS if only_team else None,
)

# Capacidad proporcional a los dias laborales del periodo
num_workdays = sum(
    1 for i in range((period_end - period_start).days + 1)
    if (period_start + timedelta(days=i)).weekday() < 5
)
capacity_period = capacity * (num_workdays / 5)  # 5 dias laborales = 1 semana
num_weeks = max(num_workdays / 5, 0.2)

summary = build_capacity_summary(tasks_df, capacity, num_weeks)

if summary.empty:
    st.warning("No hay tareas con horas en la vista seleccionada.")
    st.stop()

# ---------------- KPIs ----------------

k1, k2, k3, k4 = st.columns(4)
k1.metric("Desarrolladores", len(summary))
k2.metric("Horas programadas", round(summary["hours_scheduled"].sum(), 1))
k3.metric("Horas ejecutadas", round(summary["hours_executed"].sum(), 1))
con_cap = (summary["status"] == "Con capacidad").sum()
k4.metric("Con capacidad libre", int(con_cap))

# ---------------- Grafico de ocupacion ----------------

st.subheader("Ocupacion por desarrollador")
fig = px.bar(
    summary,
    x="developer",
    y="occupancy_pct",
    color="status",
    color_discrete_map=STATUS_COLORS,
    labels={"developer": "Desarrollador", "occupancy_pct": "% Ocupacion"},
    text="occupancy_pct",
)
fig.add_hline(y=100, line_dash="dash", line_color="red")
fig.update_traces(texttemplate="%{text}%", textposition="outside")
fig.update_layout(xaxis_tickangle=-45)
st.plotly_chart(fig, use_container_width=True)

# ---------------- Tabla resumen ----------------

st.subheader("Detalle de capacidad")
st.dataframe(
    summary.rename(
        columns={
            "developer": "Desarrollador",
            "hours_scheduled": "Horas programadas",
            "hours_executed": "Horas ejecutadas",
            "capacity_hours": "Capacidad (h)",
            "occupancy_pct": "% Ocupacion",
            "available_hours": "Horas disponibles",
            "status": "Estado",
        }
    ),
    use_container_width=True,
    hide_index=True,
)

# ---------------- Detalle de tareas por desarrollador ----------------

st.subheader("Tareas por desarrollador")
devs = ["(Todos)"] + sorted(tasks_df["developer"].unique().tolist())
sel_dev = st.selectbox("Filtrar por desarrollador", devs)
detalle = tasks_df if sel_dev == "(Todos)" else tasks_df[tasks_df["developer"] == sel_dev]
st.dataframe(
    detalle[
        ["developer", "task_name", "list_name", "hours_scheduled", "hours_executed", "status"]
    ].rename(
        columns={
            "developer": "Desarrollador",
            "task_name": "Tarea",
            "list_name": "Lista",
            "hours_scheduled": "Estimado (h)",
            "hours_executed": "Ejecutado (h)",
            "status": "Estado",
        }
    ),
    use_container_width=True,
    hide_index=True,
)

# ---------------- Exportacion ----------------

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
