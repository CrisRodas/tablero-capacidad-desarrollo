"""Transformacion de datos de ClickUp a metricas de capacidad.

Opcion C: replica la logica de la vista de Workload de ClickUp.
Las horas de cada tarea (time_estimate / time_spent) se distribuyen entre
los dias laborales de su rango start_date -> due_date, y se cuenta solo la
porcion que cae dentro del periodo seleccionado.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pandas as pd

MS_PER_HOUR = 1000 * 60 * 60


def _ms_to_hours(value) -> float:
    try:
        return round(float(value) / MS_PER_HOUR, 2)
    except (TypeError, ValueError):
        return 0.0


def _ms_to_date(value) -> date | None:
    try:
        return datetime.fromtimestamp(int(value) / 1000).date()
    except (TypeError, ValueError):
        return None


def _workdays(start: date, end: date) -> list[date]:
    """Lista de dias laborales (lun-vie) entre start y end, inclusive."""
    if start > end:
        start, end = end, start
    days = []
    d = start
    while d <= end:
        if d.weekday() < 5:  # 0=lunes ... 4=viernes
            days.append(d)
        d += timedelta(days=1)
    return days


def _overlap_fraction(
    task_start: date | None,
    task_end: date | None,
    period_start: date,
    period_end: date,
) -> float:
    """Fraccion de las horas de la tarea que cae dentro del periodo.

    Distribuye las horas de forma uniforme entre los dias laborales del
    rango de la tarea (como hace el Workload de ClickUp) y devuelve la
    proporcion de esos dias que quedan dentro del periodo seleccionado.
    """
    # Si no hay fechas, se asume que toda la carga es del periodo actual
    if task_start is None and task_end is None:
        return 1.0
    if task_start is None:
        task_start = task_end
    if task_end is None:
        task_end = task_start

    task_days = _workdays(task_start, task_end)
    if not task_days:
        # rango solo fines de semana: usar el dia tal cual
        task_days = [task_start]

    in_period = [d for d in task_days if period_start <= d <= period_end]
    return len(in_period) / len(task_days)


# Estados de ClickUp que se consideran "vigentes" para la capacidad.
# Se comparan en minusculas.
ALLOWED_STATUSES = {
    "abierto",
    "en análisis",
    "asignado",
    "en desarrollo",
    "en pruebas qa",
    "en pruebas usuario",
    "resuelto sin go live",
    "aprobado-pendiente vo.bo",
}


def tasks_to_df(
    tasks: list[dict],
    period_start: date | None = None,
    period_end: date | None = None,
    team_assignee_ids: set[str] | None = None,
    include_closed_subtasks: bool = False,
    allowed_statuses: set[str] | None = ALLOWED_STATUSES,
) -> pd.DataFrame:
    """Convierte tareas de la vista en filas por desarrollador.

    Aplica la distribucion por periodo (Opcion C) si se pasan las fechas.
    Filtra por los assignees del equipo si se pasa team_assignee_ids.
    Filtra por estados vigentes si se pasa allowed_statuses.
    """
    rows = []
    for t in tasks:
        # Filtrar por estados permitidos (vigentes)
        if allowed_statuses is not None:
            st_name = (t.get("status", {}) or {}).get("status", "").lower()
            if st_name not in allowed_statuses:
                continue

        # Excluir subtareas cerradas si aplica (como la vista de ClickUp)
        status_type = (t.get("status", {}) or {}).get("type", "")
        is_subtask = t.get("parent") is not None
        if not include_closed_subtasks and is_subtask and status_type == "closed":
            continue

        estimate_hours = _ms_to_hours(t.get("time_estimate"))
        spent_hours = _ms_to_hours(t.get("time_spent"))
        if estimate_hours == 0 and spent_hours == 0:
            continue

        # Distribucion por periodo
        if period_start and period_end:
            frac = _overlap_fraction(
                _ms_to_date(t.get("start_date")),
                _ms_to_date(t.get("due_date")),
                period_start,
                period_end,
            )
            if frac == 0:
                continue
            estimate_hours = round(estimate_hours * frac, 2)
            spent_hours = round(spent_hours * frac, 2)

        status = (t.get("status", {}) or {}).get("status", "")
        status_type_val = (t.get("status", {}) or {}).get("type", "")
        due_dt = _ms_to_date(t.get("due_date"))
        list_name = (t.get("list", {}) or {}).get("name", "")
        parent_id = t.get("parent")

        assignees = t.get("assignees", []) or []
        if team_assignee_ids:
            assignees = [
                a for a in assignees if str(a.get("id")) in team_assignee_ids
            ]

        if not assignees:
            continue

        n = len(assignees)
        share_est = round(estimate_hours / n, 2)
        share_spent = round(spent_hours / n, 2)
        for a in assignees:
            rows.append(
                {
                    "developer": a.get("username") or a.get("email") or "Sin asignar",
                    "developer_id": a.get("id"),
                    "task_name": t.get("name", ""),
                    "parent_id": parent_id,
                    "list_name": list_name,
                    "hours_scheduled": share_est,
                    "hours_executed": share_spent,
                    "status": status,
                    "status_type": status_type_val,
                    "due_date": due_dt,
                }
            )

    return pd.DataFrame(rows)


def is_active_status(status_type: str) -> bool:
    """True si el estado NO esta terminado (no es done ni closed)."""
    return status_type not in ("done", "closed")


def add_parent_names(
    df: pd.DataFrame, raw_tasks: list[dict], name_resolver=None
) -> pd.DataFrame:
    """Agrega la columna 'parent_task' con el nombre de la tarea padre.

    Usa los nombres de las tareas del lote; para padres que no esten en el
    lote, usa name_resolver(ids) -> {id: nombre} (llamadas a la API).
    """
    if df.empty or "parent_id" not in df.columns:
        df["parent_task"] = ""
        return df

    id_to_name = {t.get("id"): t.get("name", "") for t in raw_tasks}

    # Padres que faltan en el lote
    missing = {
        pid for pid in df["parent_id"].dropna().unique()
        if pid not in id_to_name
    }
    if missing and name_resolver:
        id_to_name.update(name_resolver(list(missing)))

    def _resolve(pid):
        if pid is None or (isinstance(pid, float) and pd.isna(pid)) or pid == "":
            return "(tarea principal)"
        return id_to_name.get(pid) or f"(padre {pid})"

    df["parent_task"] = df["parent_id"].map(_resolve)
    return df


def build_capacity_summary(
    tasks_df: pd.DataFrame,
    capacity_hours_per_week: float,
    num_weeks: float = 1,
    capacity_overrides: dict[str, float] | None = None,
) -> pd.DataFrame:
    """Agrupa por desarrollador y calcula ocupacion vs capacidad.

    capacity_overrides: {nombre_dev: horas_por_semana} para capacidades
    individuales (ej. part-time). El resto usa el default global.
    """
    cols = [
        "developer", "hours_scheduled", "hours_executed",
        "capacity_hours", "occupancy_pct", "available_hours", "status",
    ]
    if tasks_df.empty:
        return pd.DataFrame(columns=cols)

    overrides = capacity_overrides or {}
    weeks = max(num_weeks, 0.01)

    grouped = (
        tasks_df.groupby("developer")[["hours_scheduled", "hours_executed"]]
        .sum()
        .round(2)
        .reset_index()
    )

    grouped["capacity_hours"] = grouped["developer"].apply(
        lambda d: round(overrides.get(d, capacity_hours_per_week) * weeks, 2)
    )
    grouped["occupancy_pct"] = (
        grouped["hours_scheduled"] / grouped["capacity_hours"] * 100
    ).round(1)
    grouped["available_hours"] = (
        grouped["capacity_hours"] - grouped["hours_scheduled"]
    ).round(2)
    grouped["status"] = grouped["occupancy_pct"].apply(_capacity_status)
    return grouped.sort_values("occupancy_pct", ascending=False).reset_index(drop=True)


def _capacity_status(pct: float) -> str:
    if pct >= 100:
        return "Sobrecargado"
    if pct >= 85:
        return "A full"
    if pct >= 50:
        return "Ocupado"
    return "Con capacidad"
