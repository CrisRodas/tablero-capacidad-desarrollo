"""Cliente ligero para la API v2 de ClickUp.

Se encarga de la autenticacion, paginacion y de traer las entradas de
tiempo (ejecutado) y las tareas con sus estimados (programado).
"""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any, Iterator

import requests

BASE_URL = "https://api.clickup.com/api/v2"


class ClickUpError(Exception):
    """Error al comunicarse con la API de ClickUp."""


class ClickUpClient:
    def __init__(self, api_token: str, team_id: str):
        if not api_token:
            raise ClickUpError("Falta el token de la API de ClickUp.")
        if not team_id:
            raise ClickUpError("Falta el Team ID de ClickUp.")
        self.team_id = str(team_id)
        self._session = requests.Session()
        self._session.headers.update({"Authorization": api_token})

    def _get(self, path: str, params: dict | None = None) -> dict[str, Any]:
        url = f"{BASE_URL}{path}"
        for attempt in range(5):
            resp = self._session.get(url, params=params, timeout=30)
            if resp.status_code == 429:
                # Rate limit: esperar y reintentar
                wait = int(resp.headers.get("Retry-After", 2 ** attempt))
                time.sleep(wait)
                continue
            if not resp.ok:
                raise ClickUpError(
                    f"ClickUp respondio {resp.status_code}: {resp.text[:300]}"
                )
            return resp.json()
        raise ClickUpError("Se supero el limite de reintentos por rate limit.")

    # ----- Estructura del workspace -----

    def get_members(self) -> list[dict[str, Any]]:
        """Devuelve los miembros del workspace (desarrolladores)."""
        data = self._get(f"/team")
        teams = data.get("teams", [])
        members: list[dict[str, Any]] = []
        for team in teams:
            if str(team.get("id")) != self.team_id:
                continue
            for m in team.get("members", []):
                user = m.get("user", {})
                members.append(
                    {
                        "id": user.get("id"),
                        "username": user.get("username"),
                        "email": user.get("email"),
                    }
                )
        return members

    # ----- Tiempo ejecutado (time tracking) -----

    def get_time_entries(
        self, start: datetime, end: datetime, assignee_ids: list[int] | None = None
    ) -> list[dict[str, Any]]:
        """Trae las entradas de tiempo registradas en un rango de fechas."""
        params: dict[str, Any] = {
            "start_date": int(start.timestamp() * 1000),
            "end_date": int(end.timestamp() * 1000),
        }
        if assignee_ids:
            params["assignee"] = ",".join(str(a) for a in assignee_ids)
        data = self._get(f"/team/{self.team_id}/time_entries", params=params)
        return data.get("data", [])

    # ----- Tiempo programado (tareas con estimados) -----

    def iter_tasks(
        self, list_id: str, list_name: str | None = None
    ) -> Iterator[dict[str, Any]]:
        """Itera todas las tareas y subtareas de una lista (con paginacion)."""
        page = 0
        while True:
            data = self._get(
                f"/list/{list_id}/task",
                params={
                    "page": page,
                    "include_closed": "true",
                    "subtasks": "true",
                },
            )
            tasks = data.get("tasks", [])
            if not tasks:
                break
            for t in tasks:
                if list_name and not (t.get("list") or {}).get("name"):
                    t["list"] = {"name": list_name}
                yield t
            if data.get("last_page"):
                break
            page += 1

    def get_spaces(self) -> list[dict[str, Any]]:
        data = self._get(f"/team/{self.team_id}/space", params={"archived": "false"})
        return data.get("spaces", [])

    def get_lists_in_space(self, space_id: str) -> list[dict[str, Any]]:
        """Devuelve todas las listas de un space (folderless + dentro de folders)."""
        lists: list[dict[str, Any]] = []
        folderless = self._get(f"/space/{space_id}/list", params={"archived": "false"})
        lists.extend(folderless.get("lists", []))
        folders = self._get(f"/space/{space_id}/folder", params={"archived": "false"})
        for folder in folders.get("folders", []):
            lists.extend(folder.get("lists", []))
        return lists
