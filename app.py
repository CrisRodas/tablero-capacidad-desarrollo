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
from data_processing import (
    build_capacity_summary,
    tasks_to_df,
    time_entries_to_df,
)

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
def load_executed(token: str, team_id: str, start: datetime, end: datetime):
    client = ClickUpClient(token, team_id)
    return time_entries_to_df(client.get_time_entries(start, end))


@st.cache_data(ttl=300, show_spinner=False)
def load_scheduled(token: str, team_id: str, list_ids: tuple[str, ...]):
    client = ClickUpClient(token, team_id)
    all_tasks = []
    for lid in list_ids:
        all_tasks.extend(list(client.iter_tasks(lid)))
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
default_start = today - timedelta(days=today.weekday(), weeks=0)
col_a, col_b = st.sidebar.columns(2)
start_date = col_a.date_input("Desde", value=default_start.date())
end_date = col_b.date_input("Hasta", value=today.date())

start_dt = datetime.combine(start_date, datetime.min.time())
end_dt = datetime.combine(end_date, datetime.max.time())
num_weeks = max((end_date - start_date).days / 7, 1)

st.title("Tablero de Capacidad de Desarrollo")
st.caption("Datos extraidos de ClickUp: horas ejecutadas vs programadas")

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

st.sidebar.markdown("### Listas a incluir (programado)")
selected_list_ids: list[str] = []
for space_name, lists in spaces.items():
    with st.sidebar.expander(space_name, expanded=False):
        for lid, lname in lists:
            if st.checkbox(lname, key=f"list_{lid}"):
                selected_list_ids.append(lid)

if st.sidebar.button("Actualizar datos"):
    st.cache_data.clear()

# ---------------- Carga de datos ----------------

with st.spinner("Cargando datos de ClickUp..."):
    executed = load_executed(
        st.session_state["token"], st.session_state["team_id"], start_dt, end_dt
    )
    scheduled = (
        load_scheduled(
            st.session_state["token"],
            st.session_state["team_id"],
            tuple(selected_list_ids),
        )
        if selected_list_ids
        else pd.DataFrame()
    )

summary = build_capacity_summary(executed, scheduled, capacity, int(round(num_weeks)))

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

# ---------------- Exportacion ----------------

st.subheader("Exportar tablero")
sheets = {
    "Resumen_Capacidad": summary,
    "Horas_Ejecutadas": executed,
    "Horas_Programadas": scheduled if not scheduled.empty else pd.DataFrame(),
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
