# Inventar-App

FastAPI, PostgreSQL und MQTT für Geräteausgabe und Rückgabe.

## Starten

```powershell
docker compose up -d --build
```

- Oberfläche: http://localhost:8000/inventory
- API-Dokumentation: http://localhost:8000/docs
- Status: http://localhost:8000/health
- Downloads: `/assignments.csv` und `/assignments.xlsx`

## Tag 4

- [A: Schaden-Vermerk und Migration](docs/tag4_a.md) - Migration läuft beim API-Start.
- [B: CSV- und Excel-Export](docs/tag4_b.md) - acht fachliche Spalten ohne IDs.

## MQTT

```powershell
docker compose exec mqtt mosquitto_sub -h localhost -t "inventory/assignments/#" -v
```

Ausgabe: `inventory/assignments/issued`, Rückgabe: `inventory/assignments/returned`.
Versand nach dem Speichern mit QoS 1; Duplikate sind möglich.
Bei Broker-Ausfall bleibt die Ausleihe gespeichert, ohne spätere Nachlieferung.

## Tests

```powershell
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -p "test_tag4_*.py" -v
```
