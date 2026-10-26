ALTER TABLE architecture_diagrams ADD COLUMN error_code VARCHAR(64);
CREATE INDEX architecture_diagrams_pending_age
  ON architecture_diagrams(updated_at)
  WHERE status IN ('LOADING_MODEL', 'ANALYZING');
