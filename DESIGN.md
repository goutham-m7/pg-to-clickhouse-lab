# Design: one writable ledger, two read paths

A database operator wants to know whether a faster analytical answer is also current. Keep source, replica, and evidence distinct. Original synthetic workload only: a fixed-width order ledger (id, account, day number, net cents). No external data or services.

## Data flow and decisions

Postgres commits → built-in pgoutput publication → a single local Python consumer peeks committed transactions → ClickHouse ReplacingMergeTree stores versioned rows/tombstones → only after a synchronous insert, advance the named slot to the last decoded commit end LSN. Stable version = transaction commit position plus change ordinal. A replay may duplicate physical rows but must not change current answers. Use FINAL and filter tombstones **after** replacement. The slot starts on an empty dedicated source; no snapshot/backfill race. An outbox would be simpler but would add writes to every source transaction. An exported-snapshot bootstrap for an existing source and full PeerDB deployment are outside this lab.

Use integer money and identical, explicitly ordered query results. A benchmark alternates engine order, discards warmups and records every measured sample and actual result. Show time and size units and query scope. The UI's primary comparison comes from a recorded run; a separate API action runs both engines now. Report disagreement, not a speedup, when answers diverge. Loopback-only development services and fixed queries, no arbitrary SQL or browser-triggered writes. No distributed transaction: a query across engines does not share a snapshot. The benchmark owns an isolated source with no other writers.

## Failure and rollout

Fail closed on unknown messages, unexpected schema, missing slots and unsupported operations. Do not acknowledge partial transactions. One advisory lock protects cooperating consumers. Large source transactions must fit memory; slots retain WAL when the consumer stops. The disposable Compose project can be removed with its named volumes; never point this tool at a real database. No HA, resynchronization after loss of a volume, online DDL or production credentials.

## Acceptance and verification

| Boundary | Proof required |
|---|---|
| Decoder | Offline tests for transaction boundaries, key changes, invalid data and replay-stable versions. |
| Real databases | Insert, update, delete, rollback, replay after sink success; read current state before background merges. Record observed commit-to-sink lag. |
| Measurement | Two or more row counts including 2M; compare count/value results and on-disk storage, not estimates. |
| Console | Keyboard-usable workload and query selectors, clear source and replica labels, live success and failed-refresh states. Browser exercise against real API. |

Build sequence: protocol + real containers, reproducible workload + receipts, then read-only HTTP/React console. Test the managed contracts, not React internals, PostgreSQL crash recovery, or ClickHouse's merge implementation.
