"""Runs only against the dedicated Compose project, never a configurable DSN."""
import os

import pytest

from ledger.db import ch, postgres
from ledger.replicate import acknowledge, apply, consumer, drain, peek

pytestmark = pytest.mark.skipif(os.getenv('LAB_INTEGRATION') != '1', reason='requires local Compose databases')


def test_replay_key_move_delete_and_rollback():
    def visible():
        return ch('SELECT id,cents FROM current_ledger WHERE id IN (-2,-1) ORDER BY id')

    with postgres() as pg:
        pg.execute('DELETE FROM ledger WHERE id IN (-2,-1)')
        drain(pg)
        with consumer(pg):
            with pg.transaction():
                pg.execute('INSERT INTO ledger VALUES (-1,2,3,4)')
                pg.execute('UPDATE ledger SET cents=5 WHERE id=-1')
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
            pg.execute('UPDATE ledger SET cents=999 WHERE id=-1')
        pg.execute('UPDATE ledger SET id=-2 WHERE id=-1')
        assert drain(pg)
        assert visible() == [(-2, 5)]
        pg.execute('DELETE FROM ledger WHERE id=-2')
        drain(pg)
        assert visible() == []
        assert not peek(pg).rows


def test_competing_consumer_is_rejected():
    with postgres() as first, postgres() as second, consumer(first):
        with pytest.raises(RuntimeError, match='another lab consumer'), consumer(second):
            pytest.fail('second consumer entered critical section')
