"""At-least-once transport; slot acknowledgement happens after sink acceptance."""

import argparse
import time
from contextlib import contextmanager

from .db import ch_stream, postgres
from .protocol import decode

PG_EPOCH = 946684800


@contextmanager
def consumer(pg):
    if not pg.execute("SELECT pg_try_advisory_lock(11743, 1)").fetchone()[0]:
        raise RuntimeError("another lab consumer holds the slot")
    try:
        yield
    finally:
        pg.execute("SELECT pg_advisory_unlock(11743, 1)")


def peek(pg):
    rows = pg.execute("""SELECT data FROM pg_logical_slot_peek_binary_changes(
        'ledger_slot', NULL, 25000, 'proto_version','1','publication_names','ledger_pub')""")
    return decode(data for (data,) in rows)


def apply(batch):
    if batch.rows:
        data = "".join(
            f"{i}\t{a}\t{d}\t{c}\t{v}\t{x}\n" for i, a, d, c, v, x in batch.rows
        ).encode()
        with ch_stream("INSERT INTO versions FORMAT TabSeparated", data) as response:
            if response.read():
                raise RuntimeError(
                    "unexpected ClickHouse insert response; slot not advanced"
                )


def acknowledge(pg, batch):
    position = f"{batch.end >> 32:X}/{batch.end & 0xFFFFFFFF:X}"
    if not pg.execute(
        "SELECT end_lsn = %s::pg_lsn FROM pg_replication_slot_advance('ledger_slot', %s)",
        (position, position),
    ).fetchone()[0]:
        raise RuntimeError("slot did not reach the requested commit")


def drain(pg):
    """Commit-to-observed-visibility upper bounds (one observation per committed transaction)."""
    lags = []
    with consumer(pg):
        while (batch := peek(pg)).end:
            apply(batch)
            observed = time.time() - PG_EPOCH
            lags.extend(round((observed - t / 1e6) * 1000, 3) for t in batch.commit_us)
            acknowledge(pg, batch)
    return lags


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--watch", action="store_true", help="poll every 500 ms until interrupted"
    )
    args = parser.parse_args()
    with postgres() as pg:
        while True:
            lags = drain(pg)
            if lags:
                print(
                    f"{len(lags)} transactions; max commit-to-observation {max(lags):.1f} ms",
                    flush=True,
                )
            if not args.watch:
                break
            time.sleep(0.5)
