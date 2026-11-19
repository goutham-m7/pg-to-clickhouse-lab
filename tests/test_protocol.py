import struct

import pytest

from ledger.protocol import decode


def cols(*values):
    out = struct.pack("!H", len(values))
    for value in values:
        data = str(value).encode()
        out += b"n" if value is None else b"t" + struct.pack("!I", len(data)) + data
    return out


RID = struct.pack("!I", 42)
REL = (
    b"R"
    + RID
    + b"public\0ledger\0d\0\4"
    + b"".join(
        bytes([int(name == b"id")]) + name + b"\0" + struct.pack("!Ii", 23, -1)
        for name in (b"id", b"account", b"day", b"cents")
    )
)
BEGIN = b"B" + struct.pack("!QQI", 100, 123456, 1)
COMMIT = b"C" + struct.pack("!BQQQ", 0, 100, 108, 123456)
INSERT = b"I" + RID + b"N" + cols(7, 3, 1, 50)


def test_ordered_replay_and_primary_key_move():
    update = b"U" + RID + b"K" + cols(7, None, None, None) + b"N" + cols(8, 3, 1, 55)
    delete = b"D" + RID + b"K" + cols(8, None, None, None)
    batch = [BEGIN, REL, INSERT, update, delete, COMMIT]
    changes = decode(batch)
    assert decode(batch) == changes
    assert changes.end == 108
    assert changes.commit_us == [123456]
    assert [(r[0], r[3], r[5]) for r in changes.rows] == [
        (7, 50, 0),
        (7, 0, 1),
        (8, 55, 0),
        (8, 0, 1),
    ]
    assert [r[4] for r in changes.rows] == sorted({r[4] for r in changes.rows})


@pytest.mark.parametrize(
    "messages",
    [
        [BEGIN, REL, INSERT],
        [BEGIN, INSERT, COMMIT],
        [BEGIN, REL, b"T", COMMIT],
        [BEGIN, REL.replace(b"cents", b"taxxx"), INSERT, COMMIT],
        [BEGIN, REL, INSERT[:-1], COMMIT],
        [BEGIN, REL, INSERT + b"garbage", COMMIT],
        [COMMIT],
        [BEGIN, BEGIN, COMMIT],
    ],
)
def test_malformed_or_partial_batch_is_not_acknowledgeable(messages):
    with pytest.raises(ValueError):
        decode(messages)
