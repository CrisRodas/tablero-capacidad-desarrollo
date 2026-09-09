# Tablero de Capacidad de Desarrollo - Plataformas Alternas (ClickUp)

Dashboard que lee directamente de la vista de Workload ("Carga de trabajo")
del espacio Plataformas Alternas en ClickUp y calcula la capacidad por
persona, replicando la logica del tablero de ClickUp. Permite exportar a
Excel o CSV.

## Requisitos

- Python 3.10+
- Un API Token de ClickUp (Settings > Apps > Generate)
- Tu Team ID (en la URL: `app.clickup.com/<TEAM_ID>/...`)
- El View ID de la vista de Workload (en la URL: `.../v/wl/<VIEW_ID>`)

## Instalacion

```bash
pip install -r requirements.txt
```

Copia `.env.example` a `.env` y completa tus valores (o ingresalos en la
barra lateral de la app).

## Ejecutar

```bash
streamlit run app.py
```

Abre en http://localhost:8501. En la barra lateral:
1. Token, Team ID y View ID (ya vienen precargados si usas `.env`).
2. Capacidad estandar (horas/semana por dev).
3. Periodo a analizar (por defecto, la semana actual).
4. "Solo equipo de la vista" para filtrar a las personas configuradas.

## Como se calcula la capacidad (Opcion C)

Replica el comportamiento del Workload de ClickUp:
- **Horas programadas**: `time_estimate` de cada tarea/subtarea.
- **Horas ejecutadas**: `time_spent` (tiempo registrado).
- Las horas de cada tarea se **distribuyen entre los dias laborales** de su
  rango `start_date -> due_date`, y solo se cuenta la porcion que cae dentro
  del periodo seleccionado.
- Se excluyen subtareas cerradas y estados cancelado/rechazado (segun los
  filtros de la vista).
- **Ocupacion** = horas programadas del periodo / capacidad del periodo.
- Estado: Con capacidad (<50%), Ocupado (50-85%), A full (85-100%),
  Sobrecargado (>=100%).

## Notas

- La lista de personas del equipo esta en `TEAM_ASSIGNEE_IDS` en `app.py`,
  tomada de la configuracion de la vista. Si cambia el equipo, actualizala.
- Tareas sin fechas se cuentan completas en el periodo (no se pueden
  distribuir sin rango).
- La API de ClickUp tiene rate limits; el cliente reintenta automaticamente.
