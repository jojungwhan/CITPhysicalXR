CREATE TABLE fabric_remembered_connections (
    host_id TEXT NOT NULL,
    reconnect_action_id TEXT NOT NULL,
    requires_grounded_confirmation INTEGER NOT NULL
        CHECK (requires_grounded_confirmation IN (0, 1)),
    remembered_at TEXT NOT NULL,
    remembered_by TEXT NOT NULL,
    PRIMARY KEY (host_id, reconnect_action_id)
);

CREATE INDEX fabric_remembered_connections_by_host_time
ON fabric_remembered_connections(host_id, remembered_at DESC, reconnect_action_id);
