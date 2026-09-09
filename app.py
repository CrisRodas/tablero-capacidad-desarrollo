"""Dashboard de capacidad de desarrolladores basado en ClickUp."""

from __future__ import annotations

import io
import os
from datetime import datetime, timedelta

import pandas as pd
import plotly.express as px
import streamlit as st
from dotenv import load_dotenv

from clickup_client import ClickUpClient, ClickUpError
from data_processing import build_capacity_summary, tasks_to_df

load_dotenv()

st.set_page_config(page_title="Capacidad de Desarrollo", layout="wide")

STATUS_COLORS = {
    "Con capacidad": "#2ecc71",
    "Ocupado": "#f1c40f",
    "A full": "#e67e22",
    "Sobrecargado": "#e74c3c",
}


def get_client() -> ClickUpClient:
    token = st.session_state.get("token") or os.getenv("CLICKUP_API_TOKEN", "")
    team_id = st.session_state.get("team_id") or os.getenv("CLICKUP_TEAM_ID", "")
    return ClickUpClient(token, team_id)


@st.cache_data(ttl=300, show_spinner=False)
def load_tasks(token: str, team_id: str, list_map: tuple[tuple[str, str], ...]):
    """Carga tareas+subtareas (estimado y ejecutado) de las listas dadas."""
    client = ClickUpClient(token, team_id)
    all_tasks = []
    for lid, lname in list_map:
        all_tasks.extend(list(client.iter_tasks(lid, lname)))
    return tasks_to_df(all_tasks)


@st.cache_data(ttl=600, show_spinner=False)
def load_spaces_and_lists(token: str, team_id: str):
    client = ClickUpClient(token, team_id)
    result = {}
    for space in client.get_spaces():
        lists = client.get_lists_in_space(space["id"])
        result[space["name"]] = [(l["id"], l["name"]) for l in lists]
    return result


def to_excel_bytes(sheets: dict[str, pd.DataFrame]) -> bytes:
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        for name, df in sheets.items():
            df.to_excel(writer, sheet_name=name[:31], index=False)
    return buffer.getvalue()


# ---------------- Sidebar / configuracion ----------------

st.sidebar.title("Configuracion")
st.session_state["token"] = st.sidebar.text_input(
    "ClickUp API Token",
    value=os.getenv("CLICKUP_API_TOKEN", ""),
    type="password",
)
st.session_state["team_id"] = st.sidebar.text_input(
    "Team ID",
    value=os.getenv("CLICKUP_TEAM_ID", ""),
)
capacity = st.sidebar.number_input(
    "Capacidad (horas/semana por dev)",
    min_value=1.0,
    value=float(os.getenv("CAPACITY_HOURS_PER_WEEK", "40")),
    step=1.0,
)

today = datetime.now()
num_weeks = st.sidebar.number_input(
    "Ventana de capacidad (semanas)",
    min_value=1,
    value=1,
    step=1,
    help="Contra cuantas semanas de capacidad se compara la carga programada.",
)

st.title("Tablero de Capacidad de Desarrollo")
st.caption("Datos de ClickUp: duracion estimada (programado) vs tiempo registrado (ejecutado)")

if not st.session_state["token"] or not st.session_state["team_id"]:
    st.info("Ingresa tu API Token y Team ID en la barra lateral para comenzar.")
    st.stop()

# Seleccion de listas para el tiempo programado
try:
    spaces = load_spaces_and_lists(
        st.session_state["token"], st.session_state["team_id"]
    )
except ClickUpError as e:
    st.error(f"No se pudo conectar con ClickUp: {e}")
    st.stop()

st.sidebar.markdown("### Listas a incluir")
selected_lists: list[tuple[str, str]] = []
for space_name, lists in spaces.items():
    with st.sidebar.expander(space_name, expanded=False):
        for lid, lname in lists:
            if st.checkbox(lname, key=f"list_{lid}"):
                selected_lists.append((lid, lname))

if st.sidebar.button("Actualizar datos"):
    st.cache_data.clear()

# ---------------- Carga de datos ----------------

if not selected_lists:
    st.info("Selecciona al menos una lista en la barra lateral para ver la capacidad.")
    st.stop()

with st.spinner("Cargando datos de ClickUp..."):
    tasks_df = load_tasks(
        st.session_state["token"],
        st.session_state["team_id"],
        tuple(selected_lists),
    )

summary = build_capacity_summary(tasks_df, capacity, int(num_weeks))

# ---------------- KPIs ----------------

if summary.empty:
    st.warning("No hay datos para el rango o listas seleccionadas.")
    st.stop()

k1, k2, k3, k4 = st.columns(4)
k1.metric("Desarrolladores", len(summary))
k2.metric("Horas ejecutadas", round(summary["hours_executed"].sum(), 1))
k3.metric("Horas programadas", round(summary["hours_scheduled"].sum(), 1))
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
st.plotly_chart(fig, use_container_width=True)

# ---------------- Tabla detalle ----------------

st.subheader("Detalle de capacidad")
st.dataframe(
    summary.rename(
        columns={
            "developer": "Desarrollador",
            "hours_executed": "Horas ejecutadas",
            "hours_scheduled": "Horas programadas",
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

st.subheader("Detalle de tareas")
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
sheets = {
    "Resumen_Capacidad": summary,
    "Detalle_Tareas": tasks_df,
}
excel_bytes = to_excel_bytes(sheets)

c1, c2 = st.columns(2)
c1.download_button(
    "Descargar Excel",
    data=excel_bytes,
    file_name=f"capacidad_desarrollo_{today:%Y%m%d}.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)
c2.download_button(
    "Descargar CSV (resumen)",
    data=summary.to_csv(index=False).encode("utf-8"),
    file_name=f"capacidad_resumen_{today:%Y%m%d}.csv",
    mime="text/csv",
)
