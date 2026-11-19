"""Create a reproducible *synthetic* benchmark on an empty dedicated ledger."""

import argparse
import hashlib
import json
import platform
import time
from datetime import UTC, datetime
from pathlib import Path

from .db import ch, ch_stream, postgres
from .measure import compare, percentile, queries
from .replicate import drain


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def fingerprints(pg):
    sql = "SELECT id,account,day,cents FROM {} ORDER BY id"
    source = hashlib.sha256()
    with pg.cursor().copy("COPY (" + sql.format("ledger") + ") TO STDOUT") as copy:
        for row in copy:
            source.update(row)
    replica = hashlib.sha256()
    with ch_stream(sql.format("current_ledger") + " FORMAT TabSeparated") as stream:
        while chunk := stream.read(1 << 20):
            replica.update(chunk)
    require(source.digest() == replica.digest(), "full ordered row digest mismatch")
    return {"postgres": source.hexdigest(), "clickhouse": replica.hexdigest()}


def probe(pg):
    def observed():
        return [
            list(row) for row in ch("SELECT id,cents FROM current_ledger WHERE id=0")
        ]

    require(not observed(), "probe key already exists")
    pg.execute("INSERT INTO ledger VALUES (0,1,1,100)")
    drain(pg)
    with pg.transaction():
        pg.execute("UPDATE ledger SET cents=115 WHERE id=0")
        pg.execute("UPDATE ledger SET cents=125 WHERE id=0")
    source = pg.execute("SELECT id,cents FROM ledger WHERE id=0").fetchall()
    before = observed()
    require(
        source == [(0, 125)] and before == [[0, 100]],
        "expected stale replica during pause",
    )
    time.sleep(0.25)
    lag = drain(pg)
    after = observed()
    require(after == [[0, 125]] and len(lag) == 1, "update did not converge")
    pg.execute("DELETE FROM ledger WHERE id=0")
    deletion = drain(pg)
    deleted = observed()
    require(not deleted and len(deletion) == 1, "tombstone did not hide deleted key")
    return {
        "before_drain": before,
        "source_after_commit": source,
        "after_drain": after,
        "after_delete": deleted,
        "pause_ms": 250,
        "update_observed_ms": lag[0],
        "delete_observed_ms": deletion[0],
    }


def stage(pg, target, start, runs):
    lags = []
    for low in range(start + 1, target + 1, 25000):
        high = min(target, low + 24999)
        pg.execute(
            """INSERT INTO ledger SELECT i, (i::bigint * 7919 %% 32749)::int,
            ((i-1)/1000) %% 365, (hashint4extended(i, 42) & 2147483647) %% 100000 + 1
            FROM generate_series(%s::int, %s::int) i""",
            (low, high),
        )
        lags.extend(drain(pg))
    pg.execute("ANALYZE ledger")
    observed = {
        "postgres": pg.execute("SELECT count(*) FROM ledger").fetchone()[0],
        "clickhouse": int(ch("SELECT count() FROM current_ledger")[0][0]),
    }
    require(
        observed == {"postgres": target, "clickhouse": target},
        "live row counts disagree",
    )
    hashes = fingerprints(pg)
    sizes = {
        "postgres": pg.execute("SELECT pg_total_relation_size('ledger')").fetchone()[0],
        "clickhouse": int(
            ch(
                "SELECT sum(bytes_on_disk) FROM system.parts WHERE active AND database='lab' AND table='versions'"
            )[0][0]
        ),
    }
    results = {}
    for key, q in queries.items():
        samples = {"postgres": [], "clickhouse": []}
        for i in range(runs + 1):
            pair = compare(pg, key, reverse=i % 2 == 1)
            require(pair["equal"], f"{key} answers disagree")
            if i:  # first pair is warmup
                for name, values in samples.items():
                    values.append(pair[name]["ms"])
        results[key] = {
            "title": q.title,
            "columns": q.columns,
            "sql": q.sql,
            "rows": pair["postgres"]["rows"],
            "samples_ms": samples,
            "p50_ms": {k: percentile(v, 0.5) for k, v in samples.items()},
            "p95_ms": {k: percentile(v, 0.95) for k, v in samples.items()},
        }
    return {
        "rows": observed,
        "bytes": sizes,
        "digest": hashes,
        "queries": results,
        "commit_lags_ms": lags,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sizes", type=int, nargs="+", default=[10000, 250000, 2000000]
    )
    parser.add_argument("--runs", type=int, default=11)
    parser.add_argument("--output", type=Path, default=Path("artifacts/latest.json"))
    args = parser.parse_args()
    if (
        args.runs < 1
        or args.sizes != sorted(set(args.sizes))
        or not 1 <= min(args.sizes) <= max(args.sizes) <= 5000000
    ):
        parser.error(
            "use increasing, unique sizes from 1–5,000,000 and at least one measured run"
        )
    with postgres() as pg:
        require(
            not pg.execute("SELECT EXISTS(SELECT FROM ledger)").fetchone()[0],
            "source must be empty; use fresh lab volumes",
        )
        report = {
            "synthetic": True,
            "started_at": datetime.now(UTC).isoformat(),
            "postgres_version": pg.execute("SHOW server_version").fetchone()[0],
            "clickhouse_version": ch("SELECT version()")[0][0],
            "client_arch": platform.machine(),
            "runs": args.runs,
            "mutation_probe": probe(pg),
            "stages": [],
        }
        start = 0
        for target in args.sizes:
            report["stages"].append(stage(pg, target, start, args.runs))
            print(
                f"{target:,} rows: full digest and all paired query results match",
                flush=True,
            )
            start = target
        report["finished_at"] = datetime.now(UTC).isoformat()
        args.output.parent.mkdir(parents=True, exist_ok=True)
        temp = args.output.with_suffix(".tmp")
        temp.write_text(json.dumps(report, indent=2) + "\n")
        temp.replace(args.output)
        print(args.output)


if __name__ == "__main__":
    main()
