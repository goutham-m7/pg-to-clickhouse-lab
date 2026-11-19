"""Mirrored queries: only the relation name changes between engines."""

from dataclasses import dataclass
from math import ceil
from time import perf_counter_ns

from .db import ch


@dataclass(frozen=True)
class Query:
    title: str
    columns: list[str]
    sql: str


queries = {
    "leaders": Query(
        "Highest grossing accounts",
        ["Account", "Net cents"],
        "SELECT account, sum(cents) AS net FROM {table} GROUP BY account ORDER BY net DESC, account LIMIT 10",
    ),
    "daily": Query(
        "First week by day",
        ["Day", "Orders", "Net cents"],
        "SELECT day, count(*), sum(cents) FROM {table} WHERE day < 7 GROUP BY day ORDER BY day",
    ),
    "lookup": Query(
        "One order by primary key",
        ["Order", "Account", "Day", "Cents"],
        "SELECT id, account, day, cents FROM {table} WHERE id = 42",
    ),
}


def percentile(samples, quantile):
    return sorted(samples)[ceil(len(samples) * quantile) - 1]


def run(pg, key, engine):
    query = queries[key]
    start = perf_counter_ns()
    if engine == "postgres":
        rows = pg.execute(query.sql.format(table="ledger")).fetchall()
    elif engine == "clickhouse":
        rows = ch(query.sql.format(table="current_ledger"))
    else:
        raise ValueError("unknown engine")
    answer = [[int(value) for value in row] for row in rows]
    return {"rows": answer, "ms": round((perf_counter_ns() - start) / 1e6, 3)}


def compare(pg, key, reverse=False):
    engines = ("clickhouse", "postgres") if reverse else ("postgres", "clickhouse")
    result = {name: run(pg, key, name) for name in engines}
    result["equal"] = result["postgres"]["rows"] == result["clickhouse"]["rows"]
    return result
