CREATE TABLE ledger (
    id integer PRIMARY KEY,
    account integer NOT NULL,
    day integer NOT NULL,
    cents integer NOT NULL
);
CREATE PUBLICATION ledger_pub FOR TABLE ledger;
SELECT pg_create_logical_replication_slot('ledger_slot', 'pgoutput');
