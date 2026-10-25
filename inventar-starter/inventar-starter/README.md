# Inventar Starter

## Tag 4 A: Schaden-Vermerk

Die Rückgabe unterstützt jetzt das optionale Feld `damage_note` in Formular und API.
Beim Start über `docker compose up -d --build` wird die Alembic-Migration automatisch
ausgeführt. Die Anleitung mit Begründung und Upgrade-/Downgrade-Demo steht in
[docs/tag4_a.md](docs/tag4_a.md).

Arbeitsbasis für **Tag 3**. Dieses Projekt ist bewusst **nicht fertig**, sondern soll euch einen praktikablen Einstieg geben:

- Infrastruktur ist vorbereitet
- UI- und Form-Support ist vorhanden
- MQTT kann sofort getestet werden
- die eigentliche Inventar-Domäne baut ihr selbst

Der `grades-starter` dient daneben als **Referenzprojekt** für Struktur, Formulare, Templates und CRUD-Muster.

## Enthalten

- FastAPI
- PostgreSQL
- MQTT (Eclipse Mosquitto)
- Jinja-Templates
- `python-multipart` für HTML-Formulare
- Startseite, `/health`, `/docs`, `/inventory`
- MQTT-Publish-Endpunkt `/mqtt/publish`

## Schnellstart

```bash
docker compose up -d --build
```

Danach prüfen:

```bash
open http://localhost:8000/
open http://localhost:8000/health
open http://localhost:8000/inventory
open http://localhost:8000/docs
```

## Eure Aufgabe

Ergänzt in diesem Projekt:

- das Inventar-Schema in `db/init/010_inventory_schema.sql`
- Seed-Daten für eure Domäne
- Endpunkte für `devices` und `assignments`
- Domänenregeln wie eindeutige Seriennummern und max. eine aktive Ausleihe
- eine einfache Inventar-Oberfläche

## MQTT testen

Subscriber:

```bash
mosquitto_sub -h localhost -t "inventory/#" -v
```

Publish über die API:

```bash
curl -X POST "http://localhost:8000/mqtt/publish?topic=inventory/test&payload=hello"
```

## G) MQTT-Ereignisse für Ausleihen

Bei einer erfolgreichen Ausgabe sendet die App auf `inventory/assignments/issued`.
Bei einer erfolgreichen Rückgabe sendet sie auf `inventory/assignments/returned`.
Die Ereignisse werden nach dem Speichern der Datenbankänderung mit QoS 1 und ohne retain gesendet.
Abgelehnte Aktionen erzeugen kein Ereignis.

Ein Subscriber kann im Projektverzeichnis gestartet werden:

```powershell
docker compose exec mqtt mosquitto_sub -h localhost -t "inventory/assignments/#" -v
```

Mit lokal installiertem mosquitto funktioniert alternativ:

```powershell
mosquitto_sub -h localhost -p 1883 -t "inventory/assignments/#" -v
```

Während der Subscriber läuft, unter http://localhost:8000/inventory ein freies Gerät ausgeben und anschließend zurückgeben.
Im Terminal erscheinen beide Topics mit JSON-Nachrichten, beispielsweise bei einer Ausgabe:

```json
{
  "assignment_id": 4,
  "device_id": 2,
  "person_id": 1,
  "issued_at": "2026-10-24T12:00:00+00:00",
  "returned_at": null
}
```

Bei der Rückgabe enthält `returned_at` den Rückgabezeitpunkt.
Die IDs und Zeitangaben entsprechen jeweils dem tatsächlich gespeicherten Datensatz.

Bei einem Broker-Ausfall bleibt die Datenbankänderung gespeichert. Der Fehler steht im API-Log:

```powershell
docker compose logs api
```

Es gibt keine dauerhafte Warteschlange für späteren Versand. QoS 1 kann bei Übertragungswiederholungen Duplikate liefern.
