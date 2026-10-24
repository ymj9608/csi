CREATE TABLE project_verification_profiles (
 project_id uuid NOT NULL REFERENCES projects(id), version integer NOT NULL,
 config jsonb NOT NULL, config_digest text NOT NULL, validation jsonb,
 created_at timestamptz NOT NULL DEFAULT now(), validated_at timestamptz,
 PRIMARY KEY(project_id, version), UNIQUE(project_id,config_digest)
);
ALTER TABLE projects ADD COLUMN verification_profile_version integer;
ALTER TABLE projects ADD CONSTRAINT project_profile_fk FOREIGN KEY(id,verification_profile_version)
 REFERENCES project_verification_profiles(project_id,version);
ALTER TABLE coding_proposals ADD COLUMN execution_plan jsonb;
ALTER TABLE coding_proposals ADD COLUMN plan_digest text;
DROP INDEX idx_coding_active;
CREATE UNIQUE INDEX idx_coding_active_legacy ON coding_proposals(scan_id)
 WHERE plan_digest IS NULL AND status IN ('QUEUED','RUNNING','READY','APPROVED');
CREATE UNIQUE INDEX idx_coding_active_plan ON coding_proposals(scan_id,plan_digest)
 WHERE plan_digest IS NOT NULL AND status IN ('QUEUED','RUNNING','READY','APPROVED');
CREATE TABLE coding_workers (
 repository text PRIMARY KEY, capabilities jsonb NOT NULL, seen_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE coding_verification_runs (
 proposal_id uuid NOT NULL REFERENCES coding_proposals(id), attempt integer NOT NULL,
 report jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY(proposal_id,attempt)
);
