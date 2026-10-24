from fastapi import FastAPI, HTTPException, Request, Query, Response
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse
import os
from .db import get_conn
import paho.mqtt.client as mqtt
import psycopg
from .models import Assignment, AssignmentCreate, AssignmentReturn, Device, DeviceCreate

app = FastAPI(title="Inventar Starter", version="0.1.0")
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "templates"))

MQTT_HOST = os.getenv("MQTT_HOST", "mqtt")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))

def mqtt_client() -> mqtt.Client:
    c = mqtt.Client()
    c.connect(MQTT_HOST, MQTT_PORT, keepalive=30)
    return c

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
async def inventory_page(request: Request):
    return templates.TemplateResponse("inventory.html", {"request": request, "title": "Inventar Starter"})

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
    with get_conn() as conn:
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
    return assignment


@app.post("/assignments/{assignment_id}/return", response_model=Assignment, tags=["Ausleihen"])
def return_assignment(assignment_id: int, data: AssignmentReturn | None = None):
    with get_conn() as conn:
        assignment = conn.execute(
            "SELECT * FROM assignment WHERE assignment_id = %s FOR UPDATE", (assignment_id,)
        ).fetchone()
        if assignment is None:
            raise HTTPException(404, "Ausleihe nicht gefunden.")
        if assignment["returned_at"] is not None:
            raise HTTPException(409, "Das Gerät wurde bereits zurückgegeben.")
        assignment = conn.execute(
            "UPDATE assignment SET returned_at = COALESCE(%s, now()) WHERE assignment_id = %s RETURNING *",
            (data.returned_at if data else None, assignment_id),
        ).fetchone()
    return assignment
