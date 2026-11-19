import json
from pathlib import Path

from ledger.measure import percentile, queries


def test_nearest_rank_reports_observed_tail_not_interpolation():
    samples = list(range(1, 12))
    assert percentile(samples, 0.95) == 11
    assert percentile(samples, 0.5) == 6


def test_recorded_summaries_are_reproducible_from_raw_observations():
    report = json.loads((Path(__file__).parents[1] / "evidence/run.json").read_text())
    assert report["synthetic"] is True
    for stage in report["stages"]:
        assert stage["digest"]["postgres"] == stage["digest"]["clickhouse"]
        assert stage["rows"]["postgres"] == stage["rows"]["clickhouse"]
        for key, measurement in stage["queries"].items():
            assert measurement["sql"] == queries[key].sql
            for engine, times in measurement["samples_ms"].items():
                assert len(times) == report["runs"] and min(times) > 0
                assert percentile(times, 0.5) == measurement["p50_ms"][engine]
                assert percentile(times, 0.95) == measurement["p95_ms"][engine]
