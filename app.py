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
    )
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

    st.header(f"👤 {dev}")

    # KPIs principales
    desviacion = round(row["hours_executed"] - row["hours_scheduled"], 1)
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Estimado (h)", f"{row['hours_scheduled']:.1f}")
    m2.metric("Ejecutado (h)", f"{row['hours_executed']:.1f}")
    m3.metric("Desviacion (h)", f"{desviacion:+.1f}",
              help="Ejecutado - Estimado. Positivo = tardo mas de lo estimado.")
    m4.metric("% Ocupacion", f"{row['occupancy_pct']:.0f}%")
    m5.metric("Estado", row["status"])

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
    st.plotly_chart(fig, use_container_width=True)

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
            st.plotly_chart(fig_pie, use_container_width=True)
        else:
            st.caption("Sin horas estimadas por lista.")

    with col_b:
        st.subheader("Resumen")
        n_tasks = len(dev_tasks)
        n_activas = int((~dev_tasks["status"].str.lower().isin(
            ["completado", "cerrado", "closed", "done", "liberado"]
        )).sum())
        avance = (row["hours_executed"] / row["hours_scheduled"] * 100
                  if row["hours_scheduled"] else 0)
        st.metric("Tareas asignadas", n_tasks)
        st.metric("Tareas activas", n_activas)
        st.metric("Avance (ejec/estim)", f"{avance:.0f}%")
        libre = capacity_hours - row["hours_scheduled"]
        st.metric("Horas libres en el periodo", f"{libre:.1f}")

    # Tabla de tareas con desviacion
    st.subheader("Detalle de tareas")
    detalle = dev_tasks.copy()
    detalle["desviacion"] = (detalle["hours_executed"] - detalle["hours_scheduled"]).round(1)
    st.dataframe(
        detalle[
            ["task_name", "list_name", "hours_scheduled", "hours_executed", "desviacion", "status"]
        ].rename(columns={
            "task_name": "Tarea",
            "list_name": "Lista",
            "hours_scheduled": "Estimado (h)",
            "hours_executed": "Ejecutado (h)",
            "desviacion": "Desviacion (h)",
            "status": "Estado",
        }),
        use_container_width=True,
        hide_index=True,
    )


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
    # KPIs
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Desarrolladores", len(summary))
    k2.metric("Horas programadas", round(summary["hours_scheduled"].sum(), 1))
    k3.metric("Horas ejecutadas", round(summary["hours_executed"].sum(), 1))
    con_cap = (summary["status"] == "Con capacidad").sum()
    k4.metric("Con capacidad libre", int(con_cap))

    st.subheader("Carga de trabajo por desarrollador")
    st.caption(
        f"Haz click en una barra para ver el detalle de esa persona. "
        f"Linea roja = capacidad del periodo ({capacity_hours:.0f}h)."
    )
    fig = build_workload_chart(tasks_df, summary, capacity_hours)
    event = st.plotly_chart(
        fig, use_container_width=True, on_select="rerun", key="workload_chart"
    )

    # Capturar click en una barra -> abrir vista de esa persona
    points = (event.get("selection", {}) or {}).get("points", []) if event else []
    if points:
        clicked_dev = points[0].get("y")
        if clicked_dev:
            st.session_state.selected_dev = clicked_dev
            st.rerun()

    # Alternativa: seleccionar por lista desplegable
    st.caption("O selecciona una persona:")
    devs = sorted(summary["developer"].tolist())
    col_sel, col_btn = st.columns([3, 1])
    pick = col_sel.selectbox("Desarrollador", devs, label_visibility="collapsed")
    if col_btn.button("Ver detalle"):
        st.session_state.selected_dev = pick
        st.rerun()

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
