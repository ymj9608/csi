CREATE TABLE coding_proposals (
 id uuid PRIMARY KEY, scan_id uuid NOT NULL REFERENCES scans(id),
 profile text NOT NULL DEFAULT 'lichu-signup-v1',
 status text NOT NULL CHECK(status IN ('QUEUED','RUNNING','READY','BLOCKED','FAILED','APPROVED','REJECTED')),
 lease_token uuid, lease_until timestamptz, result jsonb, error_code text,
 created_at timestamptz NOT NULL DEFAULT now(), finished_at timestamptz,
 decided_by text, decided_at timestamptz
);
CREATE UNIQUE INDEX idx_coding_active ON coding_proposals(scan_id) WHERE status IN ('QUEUED','RUNNING','READY','APPROVED');
CREATE INDEX idx_coding_queue ON coding_proposals(status,created_at);
