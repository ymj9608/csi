CREATE TABLE scan_visual_reviews (
 scan_id uuid PRIMARY KEY REFERENCES scans(id) ON DELETE CASCADE,
 diagram_id uuid NOT NULL,
 image bytea NOT NULL,
 content_type text NOT NULL,
 image_sha256 varchar(64) NOT NULL,
 result jsonb,
 created_at timestamptz NOT NULL DEFAULT now(),
 finished_at timestamptz
);
