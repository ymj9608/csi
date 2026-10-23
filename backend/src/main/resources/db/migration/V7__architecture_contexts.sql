-- Diagram interpretations are advisory context, never security findings or scan results.
CREATE TABLE project_architectures (
 id uuid PRIMARY KEY,
 project_id uuid NOT NULL REFERENCES projects(id),
 version integer NOT NULL CHECK(version > 0),
 image_sha256 varchar(64) NOT NULL CHECK(image_sha256 ~ '^[a-f0-9]{64}$'),
 image_content_type text NOT NULL CHECK(image_content_type IN ('image/png','image/jpeg')),
 image_width integer NOT NULL CHECK(image_width > 0),
 image_height integer NOT NULL CHECK(image_height > 0),
 image_bytes bytea NOT NULL CHECK(octet_length(image_bytes) BETWEEN 1 AND 5242880),
 model text NOT NULL,
 prompt_version text NOT NULL,
 source_commit_sha varchar(40) NOT NULL DEFAULT '' CHECK(source_commit_sha = '' OR source_commit_sha ~ '^[a-f0-9]{40}$'),
 status text NOT NULL CHECK(status IN ('QUEUED','RUNNING','READY','FAILED')),
 lease_token uuid, lease_until timestamptz,
 result jsonb, error_code text,
 created_by text NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(), finished_at timestamptz,
 UNIQUE(project_id,version),
 UNIQUE(project_id,image_sha256,model,prompt_version,source_commit_sha),
 CHECK(image_width::bigint * image_height <= 16000000)
);
CREATE INDEX idx_architecture_queue ON project_architectures(status,created_at);
