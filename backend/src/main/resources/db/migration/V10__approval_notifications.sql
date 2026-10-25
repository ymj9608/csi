-- Preserve existing approvals while allowing independent proposal notifications.
ALTER TABLE approvals DROP CONSTRAINT approvals_scan_id_key;
ALTER TABLE approvals ADD COLUMN proposal_id uuid REFERENCES coding_proposals(id);

-- Earlier demo notifications were incorrectly left waiting for a second approval.
UPDATE approvals SET status='APPROVED',decided_at=coalesce(decided_at,created_at)
WHERE action='CODING_PROPOSAL_APPROVED' AND status='PENDING';

CREATE UNIQUE INDEX approvals_scan_action_unique ON approvals(scan_id,action)
WHERE proposal_id IS NULL;
CREATE UNIQUE INDEX approvals_proposal_action_unique ON approvals(proposal_id,action)
WHERE proposal_id IS NOT NULL;
CREATE INDEX approvals_scan_idx ON approvals(scan_id);
