-- Pin the selected image at proposal creation; later uploads cannot alter queued work.
ALTER TABLE projects ADD COLUMN coding_architecture_id uuid REFERENCES project_architectures(id);
ALTER TABLE coding_proposals ADD COLUMN architecture_id uuid REFERENCES project_architectures(id);
