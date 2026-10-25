# Tag 4 A: Schaden-Vermerk

## 1. Idee

Schäden bei der Rückgabe einer Ausleihe festhalten, z. B. „Display zerkratzt“.

## 2. Attribut

- `assignment.damage_note`: optionales `TEXT`-Feld.
- Englisch passend zum Schema; `TEXT` für freie Beschreibungen.
- `NULL` bedeutet: kein Vermerk erfasst. Leere Eingaben werden ebenfalls `NULL`.

## 3. Abgabe

`upgrade()` ergänzt die Spalte, `downgrade()` entfernt sie samt Vermerken.
Vorwärts und rückwärts auf PostgreSQL erfolgreich getestet.
