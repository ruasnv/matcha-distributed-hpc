DROP TABLE IF EXISTS providers;
DROP TABLE IF EXISTS tasks;

CREATE TABLE providers (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    gpus TEXT NOT NULL, -- Stored as JSON string
    address TEXT NOT NULL,
    last_seen TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    status TEXT NOT NULL DEFAULT 'active'
);

CREATE TABLE tasks (
    id TEXT PRIMARY KEY,
    consumer_id TEXT NOT NULL,
    docker_image TEXT NOT NULL,
    gpu_requirements TEXT, -- Stored as JSON string
    provider_id TEXT, -- NULLable if task is queued and not yet assigned
    gpu_assigned TEXT, -- Stored as JSON string
    status TEXT NOT NULL,
    submission_time TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_update TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    start_time TIMESTAMP,
    end_time TIMESTAMP,
    error_message TEXT,
    stdout TEXT,
    stderr TEXT
);