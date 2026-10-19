-- Keep the business-facing summary aligned with observed graph finalization.
UPDATE agent_checkpoints c SET state='FINALIZED',updated_at=now()
WHERE EXISTS (SELECT 1 FROM scan_logs l WHERE l.scan_id=c.scan_id AND l.event_type='finalize');
