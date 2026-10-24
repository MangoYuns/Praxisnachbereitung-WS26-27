-- Aufgabe D: Inventar-Schema mit Beispieldaten.
-- PostgreSQL führt diese Datei beim Initialisieren einer neuen Datenbank aus.
-- BEGIN / COMMIT: Schema und Seed-Daten werden gemeinsam gespeichert.
BEGIN;

-- 1. Stammdaten: Abteilungen, Personen, Gerätetypen und Standorte.
CREATE TABLE department (
    department_id serial PRIMARY KEY,
    name text NOT NULL UNIQUE CHECK (btrim(name) <> '')
);

CREATE TABLE person (
    person_id serial PRIMARY KEY,
    department_id integer NOT NULL REFERENCES department(department_id),
    first_name text NOT NULL CHECK (btrim(first_name) <> ''),
    last_name text NOT NULL CHECK (btrim(last_name) <> ''),
    email text NOT NULL UNIQUE
);

CREATE TABLE device_type (
    device_type_id serial PRIMARY KEY,
    name text NOT NULL UNIQUE
);

CREATE TABLE location (
    location_id serial PRIMARY KEY,
    name text NOT NULL UNIQUE
);

-- 2. Jedes Gerät hat einen Typ, einen Standort und eine eindeutige Seriennummer.
CREATE TABLE device (
    device_id serial PRIMARY KEY,
    serial_number text NOT NULL,
    device_type_id integer NOT NULL REFERENCES device_type(device_type_id),
    location_id integer NOT NULL REFERENCES location(location_id),
    status text NOT NULL DEFAULT 'ready'
        CHECK (status IN ('ready', 'maintenance', 'retired')),
    note text,
    CONSTRAINT device_serial_number_key UNIQUE (serial_number),
    CONSTRAINT device_serial_not_blank CHECK (
        btrim(serial_number) <> '' AND serial_number = btrim(serial_number)
    )
);

-- 3. Eine Ausleihe verbindet ein Gerät mit einer Person.
-- returned_at bleibt NULL, solange das Gerät noch ausgeliehen ist.
CREATE TABLE assignment (
    assignment_id serial PRIMARY KEY,
    device_id integer NOT NULL REFERENCES device(device_id),
    person_id integer NOT NULL REFERENCES person(person_id),
    issued_at timestamptz NOT NULL DEFAULT now(),
    returned_at timestamptz,
    CONSTRAINT assignment_return_time_check CHECK (
        returned_at IS NULL OR returned_at >= issued_at
    )
);

-- Pro Gerät ist höchstens eine offene Ausleihe erlaubt.
-- Abgeschlossene Ausleihen werden vom Index nicht erfasst.
CREATE UNIQUE INDEX assignment_one_active_device
    ON assignment(device_id)
    WHERE returned_at IS NULL;

-- 4. Beispieldaten. Die IDs beginnen in der frisch angelegten DB jeweils bei 1.
INSERT INTO department (name) VALUES
    ('IT'),
    ('Verwaltung');

INSERT INTO person (department_id, first_name, last_name, email) VALUES
    (1, 'Anna', 'Koch', 'anna.koch@example.org'),
    (1, 'Ben', 'König', 'ben.koenig@example.org'),
    (2, 'Clara', 'Meier', 'clara.meier@example.org');

INSERT INTO device_type (name) VALUES
    ('Laptop'),
    ('Monitor'),
    ('Handscanner');

INSERT INTO location (name) VALUES
    ('Gebäude E'),
    ('Gebäude F'),
    ('Gebäude H');

INSERT INTO device (serial_number, device_type_id, location_id, status, note) VALUES
    ('LAP-001', 1, 1, 'ready', 'Notebook mit Netzteil'),
    ('LAP-002', 1, 2, 'ready', NULL),
    ('MON-001', 2, 1, 'ready', '27 Zoll'),
    ('SCAN-001', 3, 3, 'maintenance', 'Akku prüfen');

INSERT INTO assignment (device_id, person_id, issued_at, returned_at) VALUES
    (1, 1, now() - interval '1 day', NULL),
    (3, 2, now() - interval '3 days', now() - interval '2 days'),
    (2, 3, now() - interval '5 days', now() - interval '4 days');

COMMIT;
