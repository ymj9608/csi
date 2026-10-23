CREATE TABLE architecture_diagrams (
  id UUID PRIMARY KEY,
  project_id UUID NOT NULL UNIQUE REFERENCES projects(id),
  image BYTEA NOT NULL,
  content_type TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'QUEUED',
  components JSONB,
  summary TEXT,
  confirmed BOOLEAN NOT NULL DEFAULT false,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
