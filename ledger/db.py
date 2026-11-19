"""Loopback-only demo database clients; no environment-dependent production URLs."""

import json
import os
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import psycopg

IN_COMPOSE = os.environ.get("LAB_NETWORK") == "compose"


def postgres():
    address = "host=postgres port=5432" if IN_COMPOSE else "host=127.0.0.1 port=55438"
    return psycopg.connect(
        f"{address} dbname=lab user=lab password=local-lab connect_timeout=5",
        autocommit=True,
    )


def ch_stream(sql, data=None):
    params = {"database": "lab", "max_threads": 3, "use_query_cache": 0}
    if data is not None:
        params["wait_end_of_query"] = 1
        params["query"] = sql
    address = "clickhouse:8123" if IN_COMPOSE else "127.0.0.1:58138"
    request = Request(
        f"http://{address}/?" + urlencode(params),
        data=sql.encode() if data is None else data,
        headers={"X-ClickHouse-User": "lab", "X-ClickHouse-Key": "local-lab"},
    )
    return urlopen(request, timeout=60)


def ch(sql):
    with ch_stream(sql + " FORMAT JSONCompact") as response:
        return [tuple(row) for row in json.load(response)["data"]]
