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

## Fuente de datos y estados

Lee las tareas y subtareas de las listas del espacio **Plataformas Alternas**
(`CLICKUP_SPACE_ID`), filtrando por estado directamente en la API para
descargar solo lo vigente (carga en segundos, no minutos).

Estados analizados: abierto, en analisis, asignado, en desarrollo,
en pruebas qa, en pruebas usuario, resuelto sin go live, aprobado-pendiente
vo.bo. Se ignoran resuelto, cancelado, bloqueado, rechazado, etc.

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

## Funciones del tablero

- **Resumen ejecutivo**: ocupacion promedio, horas libres del equipo,
  personas con capacidad y precision de estimacion (ejecutado vs estimado).
- **Alertas**: lista de personas sobrecargadas y de quienes pueden recibir
  mas horas.
- **Grafico tipo Workload**: barras por persona coloreadas por estado, con
  linea de capacidad. Click en una barra abre la vista de esa persona.
- **Vista por persona**: estimado vs ejecutado por tarea, desviacion,
  distribucion por lista, tareas activas y exportacion individual a Excel.
- **Rangos rapidos**: esta semana / mes / trimestre / personalizado.
- **Capacidad por persona**: ajustable en el sidebar para part-time.
- **Formato condicional** en la tabla de ocupacion.

## Seguridad y despliegue interno

El tablero muestra datos sensibles, por lo que **requiere login** y NO debe
exponerse en internet publico. Recomendado: correrlo en un servidor/VM
interno accesible solo por la red corporativa o VPN.

### Contrasena de acceso

1. Genera el hash: `python generar_password.py`
2. Ponlo en `.env` como `APP_PASSWORD_SHA256=<hash>`

Sin contrasena configurada, la app se bloquea (fail-closed).

### Despliegue con Docker

```bash
# Con el .env ya configurado (token, team, space, password)
docker compose up -d --build
```

La app queda en el puerto 8501 del host. Para exponerla solo en la maquina
local, cambia el mapeo de puertos en docker-compose.yml a
`127.0.0.1:8501:8501`. Para el equipo, publicala tras la red interna/VPN.

### Reglas de seguridad

- El `.env` NUNCA se sube al repo (esta en .gitignore y .dockerignore).
- El token de ClickUp da acceso a todo el workspace: tratalo como secreto.
- Si un token se expone, revocalo y genera uno nuevo en ClickUp.

## Notas

- La lista de personas del equipo esta en `TEAM_ASSIGNEE_IDS` en `app.py`,
  tomada de la configuracion de la vista. Si cambia el equipo, actualizala.
- Las tareas activas se determinan por el tipo de estado de ClickUp
  (open/custom = activa; done/closed = terminada).
- Tareas sin fechas se cuentan completas en el periodo (no se pueden
  distribuir sin rango).
- La API de ClickUp tiene rate limits; el cliente reintenta automaticamente.
