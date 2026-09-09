"""Transformacion de datos de ClickUp a metricas de capacidad."""

from __future__ import annotations

from datetime import datetime

import pandas as pd

MS_PER_HOUR = 1000 * 60 * 60


def _ms_to_hours(value) -> float:
    try:
        return round(float(value) / MS_PER_HOUR, 2)
    except (TypeError, ValueError):
        return 0.0


def time_entries_to_df(entries: list[dict]) -> pd.DataFrame:
    """Convierte entradas de time tracking en un DataFrame de horas ejecutadas."""
    rows = []
    for e in entries:
        user = e.get("user", {}) or {}
        task = e.get("task", {}) or {}
        start_ms = e.get("start")
        start_dt = (
            datetime.fromtimestamp(int(start_ms) / 1000) if start_ms else None
        )
        rows.append(
            {
                "developer": user.get("username") or user.get("email") or "Sin asignar",
                "developer_id": user.get("id"),
                "task_name": task.get("name", ""),
                "hours_executed": _ms_to_hours(e.get("duration")),
                "date": start_dt,
            }
        )
    df = pd.DataFrame(rows)
    if not df.empty and df["date"].notna().any():
        df["week"] = df["date"].dt.to_period("W").astype(str)
    else:
        df["week"] = None
    return df


def tasks_to_df(tasks: list[dict]) -> pd.DataFrame:
    """Convierte tareas en un DataFrame de horas programadas (time_estimate)."""
    rows = []
    for t in tasks:
        assignees = t.get("assignees", []) or []
        estimate_hours = _ms_to_hours(t.get("time_estimate"))
        due = t.get("due_date")
        due_dt = datetime.fromtimestamp(int(due) / 1000) if due else None
        if not assignees:
            rows.append(
                {
                    "developer": "Sin asignar",
                    "developer_id": None,
                    "task_name": t.get("name", ""),
                    "hours_scheduled": estimate_hours,
                    "status": (t.get("status", {}) or {}).get("status", ""),
                    "due_date": due_dt,
                }
            )
            continue
        # Repartir el estimado en partes iguales entre los asignados
        share = round(estimate_hours / len(assignees), 2) if assignees else 0.0
        for a in assignees:
            rows.append(
                {
                    "developer": a.get("username") or a.get("email") or "Sin asignar",
                    "developer_id": a.get("id"),
                    "task_name": t.get("name", ""),
                    "hours_scheduled": share,
                    "status": (t.get("status", {}) or {}).get("status", ""),
                    "due_date": due_dt,
                }
            )
    df = pd.DataFrame(rows)
    if not df.empty and "due_date" in df and df["due_date"].notna().any():
        df["week"] = df["due_date"].dt.to_period("W").astype(str)
    else:
        df["week"] = None
    return df


def build_capacity_summary(
    executed: pd.DataFrame,
    scheduled: pd.DataFrame,
    capacity_hours_per_week: float,
    num_weeks: int = 1,
) -> pd.DataFrame:
    """Cruza ejecutado vs programado y calcula ocupacion por desarrollador."""
    exec_sum = (
        executed.groupby("developer")["hours_executed"].sum()
        if not executed.empty
        else pd.Series(dtype=float)
    )
    sched_sum = (
        scheduled.groupby("developer")["hours_scheduled"].sum()
        if not scheduled.empty
        else pd.Series(dtype=float)
    )

    summary = pd.DataFrame(
        {
            "hours_executed": exec_sum,
            "hours_scheduled": sched_sum,
        }
    ).fillna(0.0)
    summary.index.name = "developer"
    summary = summary.reset_index()

    total_capacity = capacity_hours_per_week * max(num_weeks, 1)
    summary["capacity_hours"] = total_capacity
    summary["occupancy_pct"] = (
        summary["hours_scheduled"] / total_capacity * 100
    ).round(1)
    summary["available_hours"] = (
        total_capacity - summary["hours_scheduled"]
    ).round(2)
    summary["status"] = summary["occupancy_pct"].apply(_capacity_status)
    return summary.sort_values("occupancy_pct", ascending=False)


def _capacity_status(pct: float) -> str:
    if pct >= 100:
        return "Sobrecargado"
    if pct >= 85:
        return "A full"
    if pct >= 50:
        return "Ocupado"
    return "Con capacidad"
