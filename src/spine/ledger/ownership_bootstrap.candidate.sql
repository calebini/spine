CREATE TABLE ledger_access_state (
  singleton_id INTEGER PRIMARY KEY CHECK (singleton_id = 1),
  ledger_id TEXT NOT NULL UNIQUE CHECK (typeof(ledger_id) = 'text' AND length(ledger_id) BETWEEN 1 AND 256),
  realm_id TEXT,
  mode TEXT NOT NULL,
  identity_mode TEXT,
  access_epoch INTEGER NOT NULL CHECK (typeof(access_epoch) = 'integer' AND access_epoch BETWEEN 1 AND 9223372036854775807),
  recovery_epoch INTEGER NOT NULL CHECK (typeof(recovery_epoch) = 'integer' AND recovery_epoch BETWEEN 1 AND 9223372036854775807),
  CHECK (
    (mode = 'trusted_local' AND realm_id IS NULL AND identity_mode IS NULL AND
     length(ledger_id) = 80 AND substr(ledger_id,1,16) = 'ledger_instance_' AND
     substr(ledger_id,17) NOT GLOB '*[^0-9a-f]*')
    OR
    (mode = 'multi_user' AND typeof(realm_id) = 'text' AND length(realm_id) BETWEEN 1 AND 256 AND
     typeof(identity_mode) = 'text' AND identity_mode = 'trusted_identity')
  )
);
