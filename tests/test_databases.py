"""Runs only against the dedicated Compose project, never a configurable DSN."""

import os

import pytest

from ledger.db import ch, postgres
from ledger.measure import queries
from ledger.replicate import acknowledge, apply, consumer, drain, peek

pytestmark = pytest.mark.skipif(
    os.getenv("LAB_INTEGRATION") != "1", reason="requires local Compose databases"
)


def test_replay_key_move_delete_and_rollback():
    def visible():
        return ch("SELECT id,cents FROM current_ledger WHERE id IN (-2,-1) ORDER BY id")

    with postgres() as pg:
        pg.execute("DELETE FROM ledger WHERE id IN (-2,-1)")
        drain(pg)
        with consumer(pg):
            with pg.transaction():
                pg.execute("INSERT INTO ledger VALUES (-1,2,3,4)")
                pg.execute("UPDATE ledger SET cents=5 WHERE id=-1")
            batch = peek(pg)
            assert visible() == []
            apply(batch)
            assert visible() == [(-1, 5)]
            # Simulate losing the process after INSERT but before slot advancement.
            replay = peek(pg)
            assert replay == batch
            apply(replay)
            acknowledge(pg, replay)
        with pg.transaction(force_rollback=True):
            pg.execute("UPDATE ledger SET cents=999 WHERE id=-1")
        assert not peek(pg).end
        pg.execute("UPDATE ledger SET id=-2 WHERE id=-1")
        assert drain(pg)
        assert visible() == [(-2, 5)]
        pg.execute("DELETE FROM ledger WHERE id=-2")
        drain(pg)
        assert visible() == []
        assert not peek(pg).rows


def test_competing_consumer_is_rejected():
    with (
        postgres() as first,
        postgres() as second,
        consumer(first),
        pytest.raises(RuntimeError, match="another lab consumer"),
        consumer(second),
    ):
        pytest.fail("second consumer entered critical section")


def test_query_results_have_independent_expected_values():
    table = """(SELECT 42 AS id, 5 AS account, 6 AS day, 15 AS cents
                UNION ALL SELECT 43, 4, 7, 30
                UNION ALL SELECT 44, 5, 0, 15) AS fixture"""
    expected = {
        "leaders": [(4, 30), (5, 30)],
        "daily": [(0, 1, 15), (6, 1, 15)],
        "lookup": [(42, 5, 6, 15)],
    }
    with postgres() as pg:
        for key, rows in expected.items():
            sql = queries[key].sql.format(table=table)
            assert pg.execute(sql).fetchall() == rows
            assert [tuple(map(int, row)) for row in ch(sql)] == rows
