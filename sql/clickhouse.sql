CREATE TABLE lab.versions (
    id Int32, account Int32, day Int32, cents Int32,
    version UInt128, deleted UInt8
) ENGINE = ReplacingMergeTree(version) ORDER BY id;
CREATE VIEW lab.current_ledger AS
SELECT id, account, day, cents FROM lab.versions FINAL WHERE deleted = 0;
