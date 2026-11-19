"""Loopback-only demo database clients; no environment-dependent production URLs."""
import json
from urllib.request import Request, urlopen
from urllib.parse import urlencode

import psycopg


def postgres():
    return psycopg.connect('host=127.0.0.1 port=55438 dbname=lab user=lab password=local-lab connect_timeout=5', autocommit=True)


def ch_stream(sql, data=None):
    params = {'database': 'lab', 'max_threads': 3, 'use_query_cache': 0}
    if data is not None:
        params['query'] = sql
    request = Request('http://127.0.0.1:58138/?' + urlencode(params),
                      data=sql.encode() if data is None else data,
                      headers={'X-ClickHouse-User': 'lab', 'X-ClickHouse-Key': 'local-lab'})
    return urlopen(request, timeout=60)


def ch(sql):
    with ch_stream(sql + ' FORMAT JSONCompact') as response:
        return [tuple(row) for row in json.load(response)['data']]
