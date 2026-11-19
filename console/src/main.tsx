import { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import "./style.css";

type Pair<T> = { postgres: T; clickhouse: T };
type Query = {
  title: string;
  columns: string[];
  sql: string;
  rows: number[][];
  p50_ms: Pair<number>;
  p95_ms: Pair<number>;
};
type Stage = {
  rows: Pair<number>;
  bytes: Pair<number>;
  digest: Pair<string>;
  queries: Record<string, Query>;
  commit_lags_ms: number[];
};
type Receipt = {
  stages: Stage[];
  finished_at: string;
  runs: number;
  mutation_probe: {
    pause_ms: number;
    update_observed_ms: number;
    delete_observed_ms: number;
  };
};
type Live = Pair<{ ms: number; rows: number[][] }> & { equal: boolean };
const engines = ["postgres", "clickhouse"] as const;
const names = { postgres: "PostgreSQL", clickhouse: "ClickHouse" };
const fmt = new Intl.NumberFormat("en-US");
const ms = (n: number) => n.toFixed(2) + " ms";

async function get<T>(path: string): Promise<T> {
  const response = await fetch(path);
  if (!response.ok) throw new Error(String(response.status));
  return response.json();
}

function Rows({
  label,
  columns,
  rows,
}: {
  label: string;
  columns: string[];
  rows: number[][];
}) {
  if (!rows.length) return <p>{label}: no matching rows.</p>;
  return (
    <div className="scroll">
      <table aria-label={label}>
        <thead>
          <tr>
            {columns.map((c) => (
              <th key={c} scope="col">
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i}>
              {row.map((n, j) => (
                <td key={j}>{fmt.format(n)}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function LiveCompare({ id, query }: { id: string; query: Query }) {
  const [state, setState] = useState<"idle" | "loading" | "error" | "done">(
    "idle",
  );
  const [pair, setPair] = useState<Live | null>(null);
  async function run() {
    setState("loading");
    try {
      setPair(await get<Live>("/api/compare/" + id));
      setState("done");
    } catch {
      setState("error");
    }
  }
  return (
    <section className="live">
      <h2>Check the databases now</h2>
      <p>
        Runs this query against the current source and replica, not the selected
        historical row count.
      </p>
      <button onClick={run} disabled={state === "loading"}>
        {state === "loading" ? "Comparing…" : "Compare live databases"}
      </button>
      {state === "error" && (
        <p role="alert">
          Could not compare both databases. Start Docker Compose, then retry.
        </p>
      )}
      {state === "done" && pair && (
        <div aria-live="polite">
          <h3>{pair.equal ? "Live results match" : "Live results differ"}</h3>
          {!pair.equal && (
            <p>
              Reads were sequential. Drain the replication slot and compare
              again.
            </p>
          )}
          <div className="two">
            {engines.map((k) => (
              <div key={k}>
                <p>
                  <b>{names[k]}</b> · {ms(pair[k].ms)}
                </p>
                <Rows
                  label={"Live " + names[k] + " rows"}
                  columns={query.columns}
                  rows={pair[k].rows}
                />
              </div>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}

function Bench({ report }: { report: Receipt }) {
  const [index, setIndex] = useState(report.stages.length - 1);
  const [id, setId] = useState("leaders");
  const stage = report.stages[index],
    q = stage.queries[id];
  const max = Math.max(q.p50_ms.postgres, q.p50_ms.clickhouse);
  return (
    <>
      <div className="controls">
        <label>
          Recorded row count
          <select
            value={index}
            onChange={(e) => setIndex(Number(e.target.value))}
          >
            {report.stages.map((s, i) => (
              <option key={i} value={i}>
                {fmt.format(s.rows.postgres)}
              </option>
            ))}
          </select>
        </label>
        <label>
          Query
          <select value={id} onChange={(e) => setId(e.target.value)}>
            {Object.entries(stage.queries).map(([k, v]) => (
              <option key={k} value={k}>
                {v.title}
              </option>
            ))}
          </select>
        </label>
        <span className="badge">Synthetic ledger · recorded</span>
      </div>
      <section>
        <div className="section-head">
          <h2>{q.title}</h2>
          <span>Warm · {report.runs} pairs</span>
        </div>
        <div
          className="plot"
          aria-label="Median end-to-end latency; shorter is faster"
        >
          {engines.map((k) => (
            <div className="lane" key={k}>
              <b>{names[k]}</b>
              <div className="track">
                <div
                  className={"bar " + k}
                  style={{ width: (100 * q.p50_ms[k]) / max + "%" }}
                />
              </div>
              <strong>{ms(q.p50_ms[k])}</strong>
            </div>
          ))}
        </div>
        <p className="caption">
          Median client latency · shorter is faster. p95: PostgreSQL{" "}
          {ms(q.p95_ms.postgres)} / ClickHouse {ms(q.p95_ms.clickhouse)}.
        </p>
        <details open>
          <summary>SQL and matched result</summary>
          <pre>{q.sql.replace("{table}", "ledger")}</pre>
          <p className="caption">
            ClickHouse reads <code>current_ledger</code>, which resolves updates
            and deletes before aggregation.
          </p>
          <Rows
            label="Recorded result rows"
            columns={q.columns}
            rows={q.rows}
          />
        </details>
      </section>
      <section>
        <div className="section-head">
          <h2>Replica evidence</h2>
          <span>At measurement time</span>
        </div>
        <div className="two">
          <div>
            <h3>Physical footprint</h3>
            {engines.map((k) => (
              <p key={k}>
                {names[k]} <b>{(stage.bytes[k] / 1048576).toFixed(2)} MiB</b>
              </p>
            ))}
            <p className="caption">
              Source heap + indexes vs. active replica parts, not volume totals.
            </p>
          </div>
          <div>
            <h3>Current-state parity</h3>
            <p>
              Ordered SHA-256:{" "}
              <b>
                {stage.digest.postgres === stage.digest.clickhouse
                  ? "match"
                  : "mismatch"}
              </b>
            </p>
            <code>{stage.digest.postgres.slice(0, 18)}…</code>
            <p className="caption">
              All four columns of every visible row, ordered by key.
            </p>
          </div>
        </div>
        <h3>How stale was the replica?</h3>
        <p>
          {stage.commit_lags_ms.length} load transactions · maximum
          commit-to-observation <b>{ms(Math.max(...stage.commit_lags_ms))}</b>.
        </p>
        <p className="caption">
          Separate mutation probe: paused the consumer for{" "}
          {report.mutation_probe.pause_ms} ms. The update appeared by{" "}
          {ms(report.mutation_probe.update_observed_ms)}; deletion by{" "}
          {ms(report.mutation_probe.delete_observed_ms)}.
        </p>
      </section>
      <LiveCompare key={id + ":" + index} id={id} query={q} />
      <footer>
        Receipt recorded{" "}
        {new Date(report.finished_at)
          .toISOString()
          .slice(0, 19)
          .replace("T", " ")}{" "}
        UTC · <a href="/api/report">Raw observations (JSON)</a>
      </footer>
    </>
  );
}

function App() {
  const [report, setReport] = useState<Receipt | null>(null),
    [failed, setFailed] = useState(false),
    [request, setRequest] = useState(0);
  useEffect(() => {
    let active = true;
    setFailed(false);
    get<Receipt>("/api/report")
      .then((r) => {
        if (active) setReport(r);
      })
      .catch(() => {
        if (active) setFailed(true);
      });
    return () => {
      active = false;
    };
  }, [request]);
  return (
    <main>
      <header>
        <span className="kicker">Replication workbench</span>
        <h1>Ledger Parallax</h1>
        <p>
          One ledger, two ways to read it. Compare latency only after checking
          that both engines agree.
        </p>
      </header>
      {report ? (
        <Bench report={report} />
      ) : failed ? (
        <section>
          <p role="alert">
            Could not load the benchmark receipt. Check the report path or run
            the benchmark.
          </p>
          <button onClick={() => setRequest((n) => n + 1)}>
            Reload receipt
          </button>
        </section>
      ) : (
        <p role="status">Loading recorded measurements…</p>
      )}
    </main>
  );
}
createRoot(document.getElementById("root")!).render(<App />);
