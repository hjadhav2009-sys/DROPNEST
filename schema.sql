-- DropNest Database Schema

-- Projects table: one row per saved job
CREATE TABLE IF NOT EXISTS projects (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    created_at  INTEGER NOT NULL,
    updated_at  INTEGER NOT NULL,
    version     INTEGER DEFAULT 1,
    config_json TEXT NOT NULL,
    status      TEXT DEFAULT 'draft'
);

-- Parts table: imported shapes per project
CREATE TABLE IF NOT EXISTS parts (
    id           TEXT PRIMARY KEY,
    project_id   TEXT REFERENCES projects(id) ON DELETE CASCADE,
    name         TEXT NOT NULL,
    quantity     INTEGER DEFAULT 1,
    polygon_json TEXT NOT NULL,
    area_mm2     REAL NOT NULL,
    grain_angle  REAL,
    rotation_step REAL DEFAULT 90.0,
    allow_flip   INTEGER DEFAULT 0,
    metadata_json TEXT
);

-- Sheets table: material sheets per project
CREATE TABLE IF NOT EXISTS sheets (
    id           TEXT PRIMARY KEY,
    project_id   TEXT REFERENCES projects(id) ON DELETE CASCADE,
    width        REAL NOT NULL,
    height       REAL NOT NULL,
    material     TEXT DEFAULT '',
    cost         REAL DEFAULT 0.0,
    defect_json  TEXT DEFAULT '[]'
);

-- Placements table: nesting result placements
CREATE TABLE IF NOT EXISTS placements (
    id          TEXT PRIMARY KEY,
    project_id  TEXT REFERENCES projects(id) ON DELETE CASCADE,
    part_id     TEXT NOT NULL,
    sheet_id    TEXT NOT NULL,
    x           REAL NOT NULL,
    y           REAL NOT NULL,
    rotation    REAL DEFAULT 0.0,
    flipped     INTEGER DEFAULT 0
);

-- Materials library
CREATE TABLE IF NOT EXISTS materials (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    thickness   REAL DEFAULT 0.0,
    width       REAL,
    height      REAL,
    cost_per_sheet REAL DEFAULT 0.0,
    grain_dir   REAL
);

-- Nesting history
CREATE TABLE IF NOT EXISTS nest_history (
    id          TEXT PRIMARY KEY,
    project_id  TEXT REFERENCES projects(id) ON DELETE CASCADE,
    run_at      INTEGER NOT NULL,
    mode        TEXT NOT NULL,
    iterations  INTEGER,
    waste_pct   REAL,
    sheets_used INTEGER,
    total_cost  REAL,
    cut_time_sec REAL,
    result_json TEXT NOT NULL
);
