"""Cliente ligero para la API v2 de ClickUp.

Se encarga de la autenticacion, paginacion y de traer las entradas de
tiempo (ejecutado) y las tareas con sus estimados (programado).
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
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
            resp = self._session.get(url, params=params, timeout=60)
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
        self,
        list_id: str,
        list_name: str | None = None,
        statuses: list[str] | None = None,
    ) -> Iterator[dict[str, Any]]:
        """Itera tareas y subtareas de una lista, filtrando por estado en la API.

        statuses: lista de nombres de estado a incluir. Al filtrar en el
        origen se descargan muchas menos tareas (mucho mas rapido).
        """
        page = 0
        while True:
            params: dict[str, Any] = {
                "page": page,
                "include_closed": "true",
                "subtasks": "true",
            }
            if statuses:
                params["statuses[]"] = statuses
            data = self._get(f"/list/{list_id}/task", params=params)
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

    def get_space_tasks(
        self, space_id: str, statuses: list[str] | None = None, max_workers: int = 8
    ) -> list[dict[str, Any]]:
        """Trae todas las tareas de las listas de un espacio, en paralelo.

        Filtra por estado en la API para bajar solo lo vigente.
        """
        lists = self.get_lists_in_space(space_id)

        def fetch_list(l: dict) -> list[dict[str, Any]]:
            return list(self.iter_tasks(l["id"], l["name"], statuses=statuses))

        all_tasks: list[dict[str, Any]] = []
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            for result in pool.map(fetch_list, lists):
                all_tasks.extend(result)
        return all_tasks

    def iter_view_tasks(self, view_id: str) -> Iterator[dict[str, Any]]:
        """Itera todas las tareas de una vista (paginacion secuencial simple)."""
        page = 0
        while True:
            data = self._get(f"/view/{view_id}/task", params={"page": page})
            tasks = data.get("tasks", [])
            if not tasks:
                break
            yield from tasks
            if data.get("last_page"):
                break
            page += 1

    def get_view_tasks(
        self, view_id: str, max_workers: int = 8, on_progress=None
    ) -> list[dict[str, Any]]:
        """Trae todas las tareas de una vista en paralelo (mucho mas rapido).

        Descarga las paginas en lotes concurrentes hasta encontrar el final.
        on_progress(n_paginas, n_tareas) se llama para reportar avance.
        """
        def fetch_page(p: int) -> list[dict[str, Any]]:
            data = self._get(f"/view/{view_id}/task", params={"page": p})
            return data.get("tasks", [])

        all_tasks: list[dict[str, Any]] = []
        next_page = 0
        done = False
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            while not done:
                batch = list(range(next_page, next_page + max_workers))
                results = list(pool.map(fetch_page, batch))
                for tasks in results:
                    all_tasks.extend(tasks)
                # Solo terminamos cuando una pagina viene realmente vacia
                # (fin de la paginacion). No cortamos por paginas < 100
                # porque puede haber paginas intermedias asi.
                if any(len(r) == 0 for r in results):
                    done = True
                next_page += max_workers
                if on_progress:
                    on_progress(next_page, len(all_tasks))
        return all_tasks

    def get_view(self, view_id: str) -> dict[str, Any]:
        """Devuelve la metadata de una vista."""
        return self._get(f"/view/{view_id}").get("view", {})

    def get_task_names(
        self, task_ids: list[str], max_workers: int = 8
    ) -> dict[str, str]:
        """Resuelve el nombre de varias tareas por su ID, en paralelo."""
        if not task_ids:
            return {}

        def fetch(tid: str) -> tuple[str, str]:
            try:
                data = self._get(f"/task/{tid}")
                return tid, data.get("name", "")
            except ClickUpError:
                return tid, ""

        result: dict[str, str] = {}
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            for tid, name in pool.map(fetch, task_ids):
                result[tid] = name
        return result

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
