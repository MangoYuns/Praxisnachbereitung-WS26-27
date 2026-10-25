from fastapi import FastAPI, HTTPException, Request, Query, Response
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse
import csv
from datetime import datetime, timezone
from io import BytesIO, StringIO
import pandas as pd
import os
import json
import logging
from .db import get_conn
import paho.mqtt.client as mqtt
import psycopg
from .models import Assignment, AssignmentCreate, AssignmentReturn, Device, DeviceCreate

app = FastAPI(title="Inventar Starter", version="0.1.0")
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "templates"))

MQTT_HOST = os.getenv("MQTT_HOST", "mqtt")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
logger = logging.getLogger(__name__)


EXPORT_COLUMNS = (
    "serial_number", "device_type", "location_name", "person_name",
    "issued_at", "returned_at", "is_active", "damage_note",
)

ASSIGNMENT_SQL = """
    SELECT d.serial_number,
           t.name AS device_type, l.name AS location_name,
           p.first_name || ' ' || p.last_name AS person_name,
           a.issued_at, a.returned_at,
           (a.returned_at IS NULL) AS is_active, a.damage_note
    FROM assignment a
    JOIN device d ON d.device_id = a.device_id
    JOIN device_type t ON t.device_type_id = d.device_type_id
    JOIN location l ON l.location_id = d.location_id
    JOIN person p ON p.person_id = a.person_id
    ORDER BY a.issued_at DESC, a.assignment_id DESC
"""


def assignment_rows():
    with get_conn() as conn:
        return conn.execute(ASSIGNMENT_SQL).fetchall()


def csv_value(value):
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, bool):
        return "true" if value else "false"
    # Excel soll frei eingegebenen Text nicht als Formel ausführen.
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


@app.get("/assignments.csv", response_class=Response, tags=["Exporte"],
            responses={200: {"content": {"text/csv": {}}}})
def assignments_csv():
    output = StringIO(newline="")
    writer = csv.writer(output, delimiter=";", lineterminator="\r\n")
    writer.writerow(EXPORT_COLUMNS)
    for row in assignment_rows():
        writer.writerow([csv_value(row[column]) for column in EXPORT_COLUMNS])
    return Response(
        content=output.getvalue().encode("utf-8-sig"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="assignments.csv"'},
    )


@app.get("/assignments.xlsx", response_class=Response, tags=["Exporte"],
            responses={200: {"content": {"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": {}}}})
def assignments_xlsx():
    frame = pd.DataFrame(assignment_rows(), columns=EXPORT_COLUMNS)
    # Excel speichert keine Zeitzonen: erst nach UTC umrechnen, dann TZ entfernen.
    for column in ("issued_at", "returned_at"):
        frame[column] = pd.to_datetime(frame[column], utc=True).dt.tz_localize(None)

    output = BytesIO()
    with pd.ExcelWriter(
        output, engine="xlsxwriter", datetime_format='yyyy-mm-dd hh:mm:ss "UTC"',
        engine_kwargs={"options": {"strings_to_formulas": False, "strings_to_urls": False}},
    ) as writer:
        frame.to_excel(writer, sheet_name="Assignments", index=False)
        sheet = writer.sheets["Assignments"]
        sheet.freeze_panes(1, 0)
        sheet.autofilter(0, 0, len(frame), len(EXPORT_COLUMNS) - 1)
        sheet.hide_gridlines(2)
        header_format = writer.book.add_format({
            "bold": True, "font_color": "#FFFFFF", "bg_color": "#1F4E78",
            "valign": "vcenter",
        })
        sheet.set_row(0, 26)
        for index, column in enumerate(EXPORT_COLUMNS):
            sheet.write(0, index, column, header_format)
            if column in ("issued_at", "returned_at"):
                width = 27
            elif column == "damage_note":
                width = 48
            else:
                width = max(len(column), *(len(str(value)) for value in frame[column] if pd.notna(value)), 10) + 2
                width = min(width, 40)
            sheet.set_column(index, index, width)

    return Response(
        content=output.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="assignments.xlsx"'},
    )

def mqtt_client() -> mqtt.Client:
    c = mqtt.Client()
    c.connect(MQTT_HOST, MQTT_PORT, keepalive=30)
    return c


def publish_assignment_event(event: str, assignment: dict):
    topic = f"inventory/assignments/{event}"
    payload = {
        "assignment_id": assignment["assignment_id"],
        "device_id": assignment["device_id"],
        "person_id": assignment["person_id"],
        "issued_at": assignment["issued_at"].isoformat(),
        "returned_at": assignment["returned_at"].isoformat() if assignment["returned_at"] else None,
    }
    client = None
    try:
        client = mqtt_client()
        client.loop_start()
        message = client.publish(topic, json.dumps(payload), qos=1, retain=False)
        message.wait_for_publish(timeout=3)
        if not message.is_published():
            raise TimeoutError("Der MQTT-Broker hat die Nachricht nicht bestätigt.")
    except Exception:
        logger.exception("Ausleihe gespeichert, aber MQTT-Ereignis auf %s konnte nicht gesendet werden.", topic)
    finally:
        if client is not None:
            client.disconnect()
            client.loop_stop()

@app.get("/health")
async def health():
    db_state = "ok"
    mqtt_state = "ok"
    try:
        with get_conn() as conn, conn.cursor() as cur:
            cur.execute("select 1")
            cur.fetchone()
    except Exception as ex:
        db_state = f"error:{type(ex).__name__}"

    try:
        c = mqtt_client()
        c.disconnect()
    except Exception as ex:
        mqtt_state = f"degraded:{type(ex).__name__}"

    return {"status": "ok" if db_state == "ok" else "degraded", "db": db_state, "mqtt": mqtt_state}

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "title": "Inventar Starter"})

@app.get("/inventory", response_class=HTMLResponse)
def inventory_page(request: Request):
    with get_conn() as conn:
        devices = conn.execute(
            """SELECT d.*, t.name AS device_type, l.name AS location,
                      a.assignment_id,
                      CASE WHEN a.assignment_id IS NULL THEN 'frei' ELSE 'ausgeliehen' END AS availability
               FROM device d
               JOIN device_type t ON t.device_type_id = d.device_type_id
               JOIN location l ON l.location_id = d.location_id
               LEFT JOIN assignment a ON a.device_id = d.device_id AND a.returned_at IS NULL
               ORDER BY d.device_id"""
        ).fetchall()
        device_types = conn.execute("SELECT * FROM device_type ORDER BY name").fetchall()
        locations = conn.execute("SELECT * FROM location ORDER BY name").fetchall()
        persons = conn.execute("SELECT * FROM person ORDER BY last_name, first_name").fetchall()
        active_assignments = conn.execute(
            """SELECT a.*, d.serial_number, p.first_name || ' ' || p.last_name AS person
               FROM assignment a
               JOIN device d ON d.device_id = a.device_id
               JOIN person p ON p.person_id = a.person_id
               WHERE a.returned_at IS NULL
               ORDER BY a.issued_at DESC, a.assignment_id DESC"""
        ).fetchall()
    available_devices = [d for d in devices if d["assignment_id"] is None and d["status"] == "ready"]
    return templates.TemplateResponse("inventory.html", {
        "request": request,
        "title": "Inventarverwaltung",
        "devices": devices,
        "device_types": device_types,
        "locations": locations,
        "persons": persons,
        "active_assignments": active_assignments,
        "available_devices": available_devices,
    })

@app.post("/mqtt/publish")
async def mqtt_publish(topic: str = Query(...), payload: str = Query(...)):
    c = mqtt_client()
    c.publish(topic, payload, qos=0, retain=False)
    c.disconnect()
    return {"ok": True, "topic": topic, "payload": payload}


@app.exception_handler(psycopg.IntegrityError)
def handle_integrity_error(request: Request, exc: psycopg.IntegrityError):
    constraint = exc.diag.constraint_name
    if isinstance(exc, psycopg.errors.UniqueViolation):
        if constraint == "device_serial_number_key":
            detail = "Die Seriennummer existiert bereits."
        else:
            detail = "Das Gerät hat bereits eine aktive Ausleihe."
        return JSONResponse(status_code=409, content={"detail": detail})
    if isinstance(exc, psycopg.errors.ForeignKeyViolation):
        if request.url.path.endswith("/delete"):
            return JSONResponse(status_code=409, content={"detail": "Das Gerät hat eine Ausleihhistorie und kann nicht gelöscht werden."})
        return JSONResponse(status_code=422, content={"detail": "Der angegebene Typ, Standort oder die Person existiert nicht."})
    if constraint == "assignment_return_time_check":
        detail = "Die Rückgabe darf nicht vor der Ausgabe liegen."
    else:
        detail = "Die Daten verletzen eine Datenbankbedingung."
    return JSONResponse(status_code=422, content={"detail": detail})


@app.get("/devices", response_model=list[Device], tags=["Geräte"])
def list_devices():
    with get_conn() as conn:
        return conn.execute("SELECT * FROM device ORDER BY device_id").fetchall()


@app.get("/devices/{device_id}", response_model=Device, tags=["Geräte"])
def get_device(device_id: int):
    with get_conn() as conn:
        device = conn.execute("SELECT * FROM device WHERE device_id = %s", (device_id,)).fetchone()
    if device is None:
        raise HTTPException(404, "Gerät nicht gefunden.")
    return device


@app.post("/devices", response_model=Device, status_code=201, tags=["Geräte"])
def create_device(data: DeviceCreate):
    with get_conn() as conn:
        device = conn.execute(
            """INSERT INTO device (serial_number, device_type_id, location_id, status, note)
               VALUES (%s, %s, %s, %s, %s) RETURNING *""",
            (data.serial_number, data.device_type_id, data.location_id, data.status, data.note),
        ).fetchone()
    return device


@app.post("/devices/{device_id}/edit", response_model=Device, tags=["Geräte"])
def update_device(device_id: int, data: DeviceCreate):
    with get_conn() as conn:
        device = conn.execute("SELECT * FROM device WHERE device_id = %s FOR UPDATE", (device_id,)).fetchone()
        if device is None:
            raise HTTPException(404, "Gerät nicht gefunden.")
        if data.status != "ready":
            active = conn.execute(
                "SELECT assignment_id FROM assignment WHERE device_id = %s AND returned_at IS NULL",
                (device_id,),
            ).fetchone()
            if active is not None:
                raise HTTPException(409, "Das ausgeliehene Gerät muss zuerst zurückgegeben werden.")
        device = conn.execute(
            """UPDATE device SET serial_number = %s, device_type_id = %s, location_id = %s,
               status = %s, note = %s WHERE device_id = %s RETURNING *""",
            (data.serial_number, data.device_type_id, data.location_id, data.status, data.note, device_id),
        ).fetchone()
    return device


@app.post("/devices/{device_id}/delete", status_code=204, tags=["Geräte"])
def delete_device(device_id: int):
    with get_conn() as conn:
        device = conn.execute("DELETE FROM device WHERE device_id = %s RETURNING device_id", (device_id,)).fetchone()
    if device is None:
        raise HTTPException(404, "Gerät nicht gefunden.")
    return Response(status_code=204)


@app.get("/assignments", response_model=list[Assignment], tags=["Ausleihen"])
def list_assignments():
    with get_conn() as conn:
        return conn.execute("SELECT * FROM assignment ORDER BY issued_at DESC, assignment_id DESC").fetchall()


@app.get("/assignments/active", response_model=list[Assignment], tags=["Ausleihen"])
def list_active_assignments():
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM assignment WHERE returned_at IS NULL ORDER BY issued_at DESC, assignment_id DESC"
        ).fetchall()


@app.post("/assignments", response_model=Assignment, status_code=201, tags=["Ausleihen"])
def create_assignment(data: AssignmentCreate):
    with get_conn() as conn, conn.transaction():
        device = conn.execute("SELECT * FROM device WHERE device_id = %s FOR UPDATE", (data.device_id,)).fetchone()
        if device is None:
            raise HTTPException(404, "Gerät nicht gefunden.")
        if device["status"] != "ready":
            raise HTTPException(409, "Das Gerät ist nicht einsatzbereit.")
        assignment = conn.execute(
            """INSERT INTO assignment (device_id, person_id, issued_at)
               VALUES (%s, %s, COALESCE(%s, now())) RETURNING *""",
            (data.device_id, data.person_id, data.issued_at),
        ).fetchone()
    publish_assignment_event("issued", assignment)
    return assignment


@app.post("/assignments/{assignment_id}/return", response_model=Assignment, tags=["Ausleihen"])
def return_assignment(assignment_id: int, data: AssignmentReturn | None = None):
    with get_conn() as conn, conn.transaction():
        assignment = conn.execute(
            "SELECT * FROM assignment WHERE assignment_id = %s FOR UPDATE", (assignment_id,)
        ).fetchone()
        if assignment is None:
            raise HTTPException(404, "Ausleihe nicht gefunden.")
        if assignment["returned_at"] is not None:
            raise HTTPException(409, "Das Gerät wurde bereits zurückgegeben.")
        assignment = conn.execute(
            """UPDATE assignment SET returned_at = COALESCE(%s, now()), damage_note = %s
               WHERE assignment_id = %s RETURNING *""",
            (data.returned_at if data else None, (data.damage_note or None) if data else None, assignment_id),
        ).fetchone()
    publish_assignment_event("returned", assignment)
    return assignment
