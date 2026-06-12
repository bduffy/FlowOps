-- 0001: the durable control-plane schema (#5).
-- The tasks table IS the jobs table (the task is the provisioning job, arch §4.6);
-- 1:1 task<->sandbox means the row lease doubles as the per-sandbox lock.

CREATE TABLE blueprints (
    key             TEXT PRIMARY KEY,
    version         INTEGER NOT NULL DEFAULT 1,
    name            TEXT NOT NULL,
    cloud           TEXT NOT NULL,
    tofu_module_ref TEXT NOT NULL,  -- pinned ref, never user-supplied (SR1)
    budget_cap_usd  NUMERIC(12, 2) NOT NULL,
    ttl_hours       INTEGER NOT NULL,
    allowed_roles   TEXT[] NOT NULL,
    availability    TEXT NOT NULL DEFAULT 'available'
);

CREATE TABLE work_requests (
    id            TEXT PRIMARY KEY,
    blueprint_key TEXT NOT NULL REFERENCES blueprints (key),
    title         TEXT NOT NULL,
    priority      TEXT NOT NULL DEFAULT 'medium',
    requester     TEXT NOT NULL,
    owner         TEXT NOT NULL,  -- who may extend/destroy (authz; SR7)
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE tasks (
    id                TEXT PRIMARY KEY,
    request_id        TEXT NOT NULL UNIQUE REFERENCES work_requests (id),
    fulfiller_type    TEXT NOT NULL DEFAULT 'automation',
    state             TEXT NOT NULL DEFAULT 'queued'
                      CHECK (state IN ('queued', 'planning', 'awaiting_gate', 'applying',
                                       'succeeded', 'failed', 'rejected',
                                       'destroying', 'destroyed')),
    -- Idempotency keys are scoped per requester (denormalized here so the unique
    -- index can enforce it) and bound to a payload fingerprint: same key with a
    -- different body is a conflict, never a silent replay of the wrong resource.
    requester         TEXT NOT NULL,
    idempotency_key   TEXT,
    idempotency_fingerprint TEXT,
    blueprint_version INTEGER,
    intent            JSONB,   -- immutable job inputs, frozen at submit
    preview           JSONB,
    run_id            TEXT,    -- actuator-run identity, pinned BEFORE side effects
    handle            JSONB,   -- written in its own tx, separate from completion:
    destroy_result    JSONB,   -- the evidence reconciliation consumes after a crash
    orphan_suspected  BOOLEAN NOT NULL DEFAULT FALSE,
    lease_owner       TEXT,
    lease_expires_at  TIMESTAMPTZ,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- At most one task per (requester, key); absent keys never collide.
CREATE UNIQUE INDEX tasks_idempotency_key_uq
    ON tasks (requester, idempotency_key) WHERE idempotency_key IS NOT NULL;

-- Shaped for #8's claim scan (FOR UPDATE SKIP LOCKED) and the reconcile sweep.
CREATE INDEX tasks_state_lease_idx ON tasks (state, lease_expires_at);

CREATE TABLE gate_records (
    id         BIGSERIAL PRIMARY KEY,
    task_id    TEXT NOT NULL REFERENCES tasks (id),
    type       TEXT NOT NULL CHECK (type IN ('approval', 'budget')),
    result     TEXT NOT NULL DEFAULT 'pending'  -- fail-closed default
               CHECK (result IN ('pending', 'pass', 'fail')),
    decided_by TEXT,
    detail     TEXT,
    decided_at TIMESTAMPTZ,
    UNIQUE (task_id, type)
);

CREATE INDEX work_requests_blueprint_key_idx ON work_requests (blueprint_key);
