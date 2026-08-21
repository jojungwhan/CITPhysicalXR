CREATE TABLE fabric_plugins (
    plugin_id TEXT NOT NULL,
    plugin_version TEXT NOT NULL,
    manifest_json TEXT NOT NULL,
    registered_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (plugin_id, plugin_version)
);

CREATE TABLE fabric_nodes (
    node_id TEXT PRIMARY KEY,
    plugin_id TEXT NOT NULL,
    plugin_version TEXT NOT NULL,
    site_id TEXT NOT NULL,
    room_id TEXT NOT NULL,
    node_json TEXT NOT NULL,
    connection_state TEXT NOT NULL,
    health_state TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    lease_expires_at TEXT NOT NULL,
    FOREIGN KEY (plugin_id, plugin_version)
        REFERENCES fabric_plugins(plugin_id, plugin_version)
);

CREATE INDEX fabric_nodes_by_room_state
ON fabric_nodes(site_id, room_id, connection_state);

CREATE TABLE fabric_course_packs (
    course_pack_id TEXT NOT NULL,
    version TEXT NOT NULL,
    course_pack_json TEXT NOT NULL,
    installed_at TEXT NOT NULL,
    installed_by TEXT NOT NULL,
    PRIMARY KEY (course_pack_id, version)
);

CREATE TABLE fabric_sessions (
    session_id TEXT PRIMARY KEY,
    course_pack_id TEXT NOT NULL,
    course_pack_version TEXT NOT NULL,
    site_id TEXT NOT NULL,
    room_id TEXT NOT NULL,
    mode TEXT NOT NULL CHECK (mode IN ('simulation', 'physical')),
    state TEXT NOT NULL CHECK (
        state IN (
            'draft',
            'ready',
            'active',
            'paused',
            'stopped',
            'emergency_stopped',
            'failed'
        )
    ),
    session_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (course_pack_id, course_pack_version)
        REFERENCES fabric_course_packs(course_pack_id, version)
);

CREATE INDEX fabric_sessions_by_room_state
ON fabric_sessions(site_id, room_id, state);

CREATE TABLE fabric_role_bindings (
    session_id TEXT NOT NULL REFERENCES fabric_sessions(session_id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    node_id TEXT NOT NULL REFERENCES fabric_nodes(node_id),
    required_capability TEXT NOT NULL,
    binding_json TEXT NOT NULL,
    PRIMARY KEY (session_id, role)
);

CREATE TABLE fabric_events (
    stream_sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id TEXT NOT NULL UNIQUE,
    session_id TEXT NOT NULL REFERENCES fabric_sessions(session_id) ON DELETE CASCADE,
    source_node_id TEXT NOT NULL REFERENCES fabric_nodes(node_id),
    source_sequence INTEGER NOT NULL,
    topic TEXT NOT NULL,
    event_json TEXT NOT NULL,
    received_at TEXT NOT NULL,
    UNIQUE (source_node_id, source_sequence)
);

CREATE INDEX fabric_events_by_session_stream
ON fabric_events(session_id, stream_sequence);

CREATE TRIGGER fabric_events_reject_update
BEFORE UPDATE ON fabric_events
BEGIN
    SELECT RAISE(ABORT, 'fabric events are append-only');
END;

CREATE TRIGGER fabric_events_reject_delete
BEFORE DELETE ON fabric_events
BEGIN
    SELECT RAISE(ABORT, 'fabric events are append-only');
END;

CREATE TABLE fabric_commands (
    command_id TEXT PRIMARY KEY,
    request_message_id TEXT NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE,
    session_id TEXT NOT NULL REFERENCES fabric_sessions(session_id) ON DELETE CASCADE,
    target_node_id TEXT NOT NULL REFERENCES fabric_nodes(node_id),
    action TEXT NOT NULL,
    priority TEXT NOT NULL,
    command_json TEXT NOT NULL,
    requested_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    terminal_stage TEXT,
    terminal_at TEXT
);

CREATE INDEX fabric_commands_by_session_time
ON fabric_commands(session_id, requested_at, command_id);

CREATE TABLE fabric_command_lifecycle (
    stream_sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id TEXT NOT NULL UNIQUE,
    command_id TEXT NOT NULL REFERENCES fabric_commands(command_id) ON DELETE CASCADE,
    stage TEXT NOT NULL,
    lifecycle_json TEXT NOT NULL,
    occurred_at TEXT NOT NULL
);

CREATE INDEX fabric_lifecycle_by_command_stream
ON fabric_command_lifecycle(command_id, stream_sequence);

CREATE INDEX fabric_lifecycle_by_time
ON fabric_command_lifecycle(occurred_at, stream_sequence);

CREATE TRIGGER fabric_lifecycle_reject_update
BEFORE UPDATE ON fabric_command_lifecycle
BEGIN
    SELECT RAISE(ABORT, 'fabric command lifecycle is append-only');
END;

CREATE TRIGGER fabric_lifecycle_reject_delete
BEFORE DELETE ON fabric_command_lifecycle
BEGIN
    SELECT RAISE(ABORT, 'fabric command lifecycle is append-only');
END;

CREATE TABLE fabric_control_leases (
    lease_id TEXT PRIMARY KEY,
    node_id TEXT NOT NULL REFERENCES fabric_nodes(node_id),
    capability TEXT NOT NULL,
    session_id TEXT NOT NULL REFERENCES fabric_sessions(session_id) ON DELETE CASCADE,
    owner_node_id TEXT,
    priority TEXT NOT NULL,
    acquired_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    released_at TEXT,
    release_reason TEXT
);

CREATE UNIQUE INDEX fabric_one_active_control_lease
ON fabric_control_leases(node_id, capability)
WHERE released_at IS NULL;

CREATE TABLE fabric_flow_debounce (
    session_id TEXT NOT NULL REFERENCES fabric_sessions(session_id) ON DELETE CASCADE,
    flow_id TEXT NOT NULL,
    source_node_id TEXT NOT NULL REFERENCES fabric_nodes(node_id),
    last_triggered_at TEXT NOT NULL,
    PRIMARY KEY (session_id, flow_id, source_node_id)
);

CREATE TABLE fabric_identities (
    identity_id TEXT PRIMARY KEY,
    actor_type TEXT NOT NULL,
    roles_json TEXT NOT NULL,
    permissions_json TEXT NOT NULL,
    site_id TEXT,
    room_id TEXT,
    session_id TEXT,
    token_hash TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    revoked_at TEXT
);

CREATE INDEX fabric_identities_by_expiry
ON fabric_identities(expires_at, revoked_at);

CREATE TABLE fabric_audit (
    audit_id TEXT PRIMARY KEY,
    actor_id TEXT NOT NULL,
    action TEXT NOT NULL,
    resource_type TEXT NOT NULL,
    resource_id TEXT,
    outcome TEXT NOT NULL CHECK (outcome IN ('succeeded', 'denied', 'failed')),
    correlation_id TEXT,
    occurred_at TEXT NOT NULL,
    details_json TEXT NOT NULL
);

CREATE INDEX fabric_audit_by_time
ON fabric_audit(occurred_at, audit_id);

CREATE INDEX fabric_audit_by_actor_time
ON fabric_audit(actor_id, occurred_at, audit_id);

CREATE TRIGGER fabric_audit_reject_update
BEFORE UPDATE ON fabric_audit
BEGIN
    SELECT RAISE(ABORT, 'fabric audit is append-only');
END;

CREATE TRIGGER fabric_audit_reject_delete
BEFORE DELETE ON fabric_audit
BEGIN
    SELECT RAISE(ABORT, 'fabric audit is append-only');
END;
