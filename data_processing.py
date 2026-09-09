"""Transformacion de datos de ClickUp a metricas de capacidad.

En este workspace las horas viven en las tareas/subtareas nativas:
- time_estimate  -> duracion estimada (horas programadas)
- time_spent     -> tiempo registrado (horas ejecutadas)
"""

from __future__ import annotations

from datetime import datetime

import pandas as pd

MS_PER_HOUR = 1000 * 60 * 60


def _ms_to_hours(value) -> float:
    try:
        return round(float(value) / MS_PER_HOUR, 2)
    except (TypeError, ValueError):
        return 0.0


def tasks_to_df(tasks: list[dict]) -> pd.DataFrame:
    """Convierte tareas/subtareas en un DataFrame por desarrollador.

    Cada fila = una tarea asignada a un desarrollador, con sus horas
    estimadas (programadas) y ejecutadas (time_spent). Si una tarea tiene
    varios asignados, las horas se reparten en partes iguales.
    """
    rows = []
    for t in tasks:
        estimate_hours = _ms_to_hours(t.get("time_estimate"))
        spent_hours = _ms_to_hours(t.get("time_spent"))
        if estimate_hours == 0 and spent_hours == 0:
            continue  # tarea sin horas: no aporta a capacidad

        assignees = t.get("assignees", []) or []
        status = (t.get("status", {}) or {}).get("status", "")
        due = t.get("due_date")
        due_dt = datetime.fromtimestamp(int(due) / 1000) if due else None
        list_name = (t.get("list", {}) or {}).get("name", "")

        if not assignees:
            rows.append(
                {
                    "developer": "Sin asignar",
                    "developer_id": None,
                    "task_name": t.get("name", ""),
                    "list_name": list_name,
                    "hours_scheduled": estimate_hours,
                    "hours_executed": spent_hours,
                    "status": status,
                    "due_date": due_dt,
                }
            )
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
                    "list_name": list_name,
                    "hours_scheduled": share_est,
                    "hours_executed": share_spent,
                    "status": status,
                    "due_date": due_dt,
                }
            )

    df = pd.DataFrame(rows)
    if not df.empty and df["due_date"].notna().any():
        df["week"] = df["due_date"].dt.to_period("W").astype(str)
    else:
        df["week"] = None
    return df


def build_capacity_summary(
    tasks_df: pd.DataFrame,
    capacity_hours_per_week: float,
    num_weeks: int = 1,
) -> pd.DataFrame:
    """Agrupa por desarrollador y calcula ocupacion vs capacidad."""
    if tasks_df.empty:
        return pd.DataFrame(
            columns=[
                "developer",
                "hours_scheduled",
                "hours_executed",
                "capacity_hours",
                "occupancy_pct",
                "available_hours",
                "status",
            ]
        )

    grouped = (
        tasks_df.groupby("developer")[["hours_scheduled", "hours_executed"]]
        .sum()
        .round(2)
        .reset_index()
    )

    total_capacity = capacity_hours_per_week * max(num_weeks, 1)
    grouped["capacity_hours"] = total_capacity
    grouped["occupancy_pct"] = (
        grouped["hours_scheduled"] / total_capacity * 100
    ).round(1)
    grouped["available_hours"] = (
        total_capacity - grouped["hours_scheduled"]
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
