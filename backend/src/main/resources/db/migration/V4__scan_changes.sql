CREATE TABLE scan_changes (
    scan_id uuid PRIMARY KEY REFERENCES scans(id) ON DELETE CASCADE,
    evidence jsonb NOT NULL,
    review jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);
