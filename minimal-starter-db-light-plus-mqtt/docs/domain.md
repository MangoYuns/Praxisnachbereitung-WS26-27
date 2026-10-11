# Domänenmodell Inventar

```mermaid
erDiagram
  Person ||--o{ Assignment : leiht
  Device ||--o{ Assignment : wird_verliehen

  Person { int person_id PK
           string personnel_number UK
           string first_name
           string last_name
           string email UK
           string department
           string location }

  Device { int device_id PK
           string device_number UK
           string type
           string model
           date purchase_date
           decimal net_price
           string location
           string status }

  Assignment { int assignment_id PK
               int person_id FK
               int device_id FK
               date assigned_at
               date returned_at }
```

## Regeln

- R1: Ein Gerät darf max. eine aktive Zuweisung haben (`returned_at` ist leer).
- R2: Zuweisungen desselben Geräts dürfen sich zeitlich nicht überschneiden.
- R3: `returned_at` darf nicht vor `assigned_at` liegen.
- R4: Ein Gerät darf erst nach dem Kaufdatum verliehen werden.

## UK/Constraint-Ideen

- UK auf `personnel_number`, `email` und `inventory_number`
- `status` nur mit festen Werten erlauben, z. B. `CHECK (status IN ('in_betrieb','defekt','ausgemustert'))`
- `CHECK (net_price > 0)`
- FKs `NOT NULL` und `ON DELETE RESTRICT`
