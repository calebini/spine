CREATE TABLE IF NOT EXISTS command_receipts (
  command_receipt_id TEXT PRIMARY KEY,
  command_id TEXT NOT NULL UNIQUE CHECK (length(command_id) > 0),
  command TEXT NOT NULL CHECK (length(command) > 0),
  actor_subject_id TEXT NOT NULL CHECK (length(actor_subject_id) > 0),
  action_timestamp_utc TEXT NOT NULL,
  effect TEXT NOT NULL CHECK (length(effect) > 0),
  item_id TEXT,
  target_version TEXT,
  result_identity_facts_json TEXT NOT NULL CHECK (length(result_identity_facts_json) > 0),
  semantic_facts_hash TEXT NOT NULL CHECK (
    length(semantic_facts_hash) = 64 AND semantic_facts_hash NOT GLOB '*[^0-9a-f]*'
  ),
  semantic_facts_json TEXT NOT NULL CHECK (length(semantic_facts_json) > 0),
  created_at_utc TEXT NOT NULL,
  FOREIGN KEY (item_id)
    REFERENCES coordination_items (item_id)
    DEFERRABLE INITIALLY DEFERRED
);

CREATE INDEX IF NOT EXISTS command_receipts_item_created_idx
ON command_receipts (item_id, created_at_utc, command_receipt_id)
WHERE item_id IS NOT NULL;
