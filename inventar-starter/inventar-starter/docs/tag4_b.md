# Tag 4 B: Exporte

## Spalten

`serial_number`, `device_type`, `location_name`, `person_name`,
`issued_at`, `returned_at`, `is_active`, `damage_note`.

IDs entfallen, da Seriennummer und Name für die fachliche Auswertung reichen.
Eine Zeile pro Ausleihe, einschließlich abgeschlossener Ausleihen.
`is_active` ist wahr, wenn die Rückgabe fehlt. Zeitangaben sind in UTC.

## Umsetzung

In `backend/app/main.py`: gemeinsame SQL-Abfrage über `assignment`, `device`,
`device_type`, `location` und `person`. Beide Endpunkte nutzen dieselben acht Spalten.

- `/assignments.csv`: Text mit `;`, Kopfzeile und UTF-8. Datentypen beim Import setzen.
- `/assignments.xlsx`: Pandas + ExcelWriter; typisierte Zellen, Filter und feste Kopfzeile.

CSV eignet sich für Datenaustausch und Power Query, XLSX zur direkten Nutzung in Excel.
Beide Downloads sind Momentaufnahmen.

## Testen

```powershell
curl.exe --fail http://localhost:8000/assignments.csv --output assignments.csv
curl.exe --fail http://localhost:8000/assignments.xlsx --output assignments.xlsx
```

Beide Exporte mit PostgreSQL abgeglichen. Acht Tests für A und B bestanden.
