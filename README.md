# Tablero de Capacidad de Desarrollo (ClickUp)

Dashboard que extrae horas ejecutadas (time tracking) y programadas
(time estimates) desde ClickUp y calcula la ocupacion/capacidad de cada
desarrollador. Permite exportar el tablero a Excel o CSV.

## Requisitos

- Python 3.10+
- Un API Token de ClickUp (Settings > Apps > Generate)
- Tu Team ID (aparece en la URL: `app.clickup.com/<TEAM_ID>/...`)

## Instalacion

```bash
pip install -r requirements.txt
```

Copia `.env.example` a `.env` y completa tus valores (opcional, tambien
puedes ingresarlos en la barra lateral de la app):

```bash
cp .env.example .env
```

## Ejecutar

```bash
streamlit run app.py
```

Se abrira en el navegador. En la barra lateral:
1. Ingresa el API Token y Team ID (si no usaste `.env`).
2. Ajusta la capacidad estandar (horas/semana por dev).
3. Elige el rango de fechas.
4. Marca las listas de ClickUp de donde tomar el tiempo programado.
5. Usa "Actualizar datos" para refrescar la cache.

## Como se calcula la capacidad

- Horas ejecutadas: suma del time tracking del rango de fechas.
- Horas programadas: suma de los `time_estimate` de las tareas de las listas
  seleccionadas, repartido en partes iguales entre los asignados.
- Ocupacion = horas programadas / (capacidad semanal x numero de semanas).
- Estado: Con capacidad (<50%), Ocupado (50-85%), A full (85-100%),
  Sobrecargado (>=100%).

## Notas

- Si tus equipos guardan las horas programadas en un custom field en vez de
  `time_estimate`, ajusta `tasks_to_df` en `data_processing.py`.
- La API de ClickUp tiene rate limits; el cliente reintenta automaticamente.
