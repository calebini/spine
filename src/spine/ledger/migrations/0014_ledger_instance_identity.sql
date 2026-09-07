CREATE TABLE ledger_instance_metadata (
  singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
  identity_contract TEXT NOT NULL CHECK (identity_contract = 'spine.ledger-instance.v1'),
  ledger_instance_id TEXT NOT NULL UNIQUE CHECK (
    length(ledger_instance_id) = 80
    AND substr(ledger_instance_id, 1, 16) = 'ledger_instance_'
    AND substr(ledger_instance_id, 17) NOT GLOB '*[^0-9a-f]*'
  ),
  origin TEXT NOT NULL CHECK (origin IN ('initialized_random_v1', 'schema13_logical_backfill_v1'))
);

CREATE TRIGGER ledger_instance_metadata_no_update
BEFORE UPDATE ON ledger_instance_metadata BEGIN
  SELECT RAISE(ABORT, 'ledger instance identity is immutable');
END;

CREATE TRIGGER ledger_instance_metadata_no_delete
BEFORE DELETE ON ledger_instance_metadata BEGIN
  SELECT RAISE(ABORT, 'ledger instance identity is immutable');
END;

CREATE TRIGGER ledger_instance_metadata_no_replace
BEFORE INSERT ON ledger_instance_metadata
WHEN EXISTS (SELECT 1 FROM ledger_instance_metadata) BEGIN
  SELECT RAISE(ABORT, 'ledger instance identity already exists');
END;
