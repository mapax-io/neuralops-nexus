"""
Trial C — txtai 9.14.0 on pgvector (THROWAWAY; de-risks Layer 3 items 31/44/24).
Delete this folder after the trial. Run against the nexus_vectors database.

Claims to verify before design:
  C1  index + semantic search works on a pgvector backend (external embedder —
      OUR code calls the embedder, txtai just receives vectors)
  C2  metadata filtering: company/project/topic as SQL WHERE on content storage
  C2b cross-company isolation (company filter never leaks other rows)
  C3  hybrid search: dense (pgvector) + keyword (pgtext scoring) combined
  C4  per-model dimensions: two tables with different dims coexist in one DB
  C5  delete by source: find ids by SQL, delete, gone from search
  C6  save/load round-trip (config reload finds the same pg tables)
"""
import hashlib
import math
import os
import tempfile
import traceback

URL = os.environ.get(
    "TRIAL_PG_URL",
    "postgresql+psycopg2://neuralops:CHANGE_ME@postgres-dev:5432/nexus_vectors",
)

results = []


def check(name, ok, detail=""):
    results.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}  {detail}")


# --- embedder: try fastembed (real), fall back to deterministic fake ---------
def make_embedder():
    try:
        from fastembed import TextEmbedding
        model = TextEmbedding("nomic-ai/nomic-embed-text-v1.5")  # 768 dims

        def transform(inputs):
            return [list(map(float, v)) for v in model.embed(list(inputs))]

        return transform, 768, "fastembed nomic-embed-text-v1.5"
    except Exception as exc:  # noqa: BLE001
        print(f"[fastembed unavailable: {type(exc).__name__}: {exc}] using fake embedder")

        def fake_one(text, dims=768):
            # deterministic pseudo-embedding; token-overlap drives similarity
            vec = [0.0] * dims
            for tok in text.lower().split():
                h = int(hashlib.md5(tok.encode()).hexdigest(), 16)
                for k in range(8):
                    vec[(h >> (k * 8)) % dims] += 1.0
            n = math.sqrt(sum(x * x for x in vec)) or 1.0
            return [x / n for x in vec]

        def transform(inputs):
            return [fake_one(t) for t in inputs]

        return transform, 768, "fake hash embedder"


transform, DIMS, EMBEDDER_NAME = make_embedder()
print(f"embedder: {EMBEDDER_NAME} ({DIMS} dims)")
print(f"database: {URL.split('@')[-1]}")

from txtai import Embeddings  # noqa: E402

DOCS = [
    ("m1", {"text": "The quarterly revenue grew twelve percent after the pricing change.",
            "company": "c1", "project": "p1", "topic": "t1", "source": "chat:t1"}),
    ("m2", {"text": "Postgres connection pooling failed under load; pgbouncer fixed it.",
            "company": "c1", "project": "p1", "topic": "t2", "source": "chat:t2"}),
    ("m3", {"text": "Our cat mascot logo should be orange, said the design team.",
            "company": "c2", "project": "p9", "topic": "t9", "source": "chat:t9"}),
    ("m4", {"text": "Database performance tuning: indexes and connection pools matter.",
            "company": "c1", "project": "p1", "topic": "t2", "source": "doc:perf-guide"}),
]


def build(table, dims_transform):
    return Embeddings(
        method="external",
        transform=dims_transform,
        backend="pgvector",
        pgvector={"url": URL, "table": table},
        content=URL,
        scoring={"method": "pgtext", "url": URL},
        hybrid=True,
    )


try:
    emb = build("trialc_vectors_main", transform)
    emb.index([(i, d, None) for i, d in DOCS])

    # C1 — semantic search
    r = emb.search("select id, text, score from txtai where similar('database pooling problems')", 4)
    c1 = bool(r) and r[0]["id"] in ("m2", "m4")
    check("C1 index+semantic search on pgvector", c1, f"top={r[0]['id'] if r else None}")

    # C2 — metadata filter (company/project/topic)
    r = emb.search(
        "select id, company, topic from txtai where similar('database pooling problems') "
        "and company = :c and project = :p and topic = :t",
        4, parameters={"c": "c1", "p": "p1", "t": "t2"})
    ids = {row["id"] for row in r}
    c2 = ids <= {"m2", "m4"} and len(ids) >= 1 and all(row["company"] == "c1" for row in r)
    check("C2 company/project/topic SQL filter", c2, f"ids={sorted(ids)}")

    # C2b — cross-company isolation: same query, other company
    r = emb.search(
        "select id from txtai where similar('database pooling problems') and company = :c",
        4, parameters={"c": "c2"})
    c2b = {row["id"] for row in r} <= {"m3"}
    check("C2b other company never sees c1 rows", c2b, f"ids={[row['id'] for row in r]}")

    # C3 — hybrid: exact keyword that only m2 contains
    r = emb.search("select id, score from txtai where similar('pgbouncer')", 4)
    c3 = bool(r) and r[0]["id"] == "m2"
    check("C3 hybrid keyword (pgtext) finds exact term", c3, f"top={r[0]['id'] if r else None}")

    # C5 — delete by source
    ids = [row["id"] for row in emb.search("select id from txtai where source = :s", 10,
                                           parameters={"s": "doc:perf-guide"})]
    deleted = emb.delete(ids)
    r = emb.search("select id from txtai where source = :s", 10, parameters={"s": "doc:perf-guide"})
    check("C5 delete by source", bool(deleted) and not r, f"deleted={deleted}")

    # C6 — reconnect: a FRESH process must find the rows already in pg WITHOUT
    # txtai's save/load of the transform (the ALLOW_RESOLVE_TRANSFORM guard
    # blocks that for external transforms). Production constructs the
    # Embeddings object fresh each start, transform passed in code. This
    # check discovers WHICH reconnect strategy txtai accepts — each is tried
    # in turn and the first that answers correctly wins.
    CFG_DIR = os.path.join(tempfile.gettempdir(), "trialc-index-config")
    e2 = None

    def strat_a():
        # fresh object, saved config dir, transform injected over the config
        emb.save(CFG_DIR)
        e = Embeddings()
        e.load(CFG_DIR, config={**emb.config, "transform": transform})
        return e

    def strat_b():
        # fresh object built from the live config dict, explicit load(config=)
        e2 = build("trialc_vectors_main", transform)
        e2.load(config={**emb.config, "transform": transform})
        return e2

    def strat_c():
        # fresh object, same config, straight to search (lazy connect)
        return build("trialc_vectors_main", transform)

    c6, won, errs = False, None, []
    for name, strat in (("saved-dir+transform-override", strat_a),
                        ("load(config=)", strat_b), ("lazy", strat_c)):
        try:
            e2 = strat()
            r = e2.search("select id from txtai where similar('revenue growth') and company='c1'", 1)
            if r and r[0]["id"] == "m1":
                c6, won = True, name
                break
            errs.append(f"{name}: wrong/empty answer {r}")
        except Exception as exc:  # noqa: BLE001
            errs.append(f"{name}: {type(exc).__name__}: {exc}")
    check("C6 fresh object reconnects to pg tables", c6,
          f"strategy={won}" if c6 else " | ".join(errs)[:300])

    # C4 — second index, DIFFERENT dimensions, same database, OWN SCHEMA.
    # The first run of this trial hung here: txtai indexes use fixed
    # content/scoring table names, so a second index in the SAME schema waits
    # on the first one's open transaction (and would clobber its content
    # tables if it got through). Design rule under test: one pg DATABASE,
    # one SCHEMA PER INDEX.
    main_config = dict(emb.config)
    emb.save(CFG_DIR)
    for handle in (e2, emb):
        if handle is None:
            continue
        try:
            handle.close()
        except Exception:  # noqa: BLE001
            pass

    def transform384(inputs):
        return [v[:384] for v in transform(inputs)]

    emb3 = Embeddings(
        method="external", transform=transform384,
        backend="pgvector",
        pgvector={"url": URL, "table": "vectors_other", "schema": "trialc_model2"},
        content=URL, scoring={"method": "pgtext", "url": URL},
        schema="trialc_model2", hybrid=True,
    )
    emb3.index([("x1", {"text": "hello small world", "company": "c1"}, None)])
    r = emb3.search("select id from txtai where similar('hello world')", 1)
    ok_new = bool(r) and r[0]["id"] == "x1"
    emb3.close()

    # ...and the ORIGINAL index must still answer afterwards (no clobber)
    e4 = Embeddings()
    e4.load(CFG_DIR, config={**main_config, "transform": transform})
    r = e4.search("select id from txtai where similar('revenue growth') and company='c1'", 1)
    ok_old = bool(r) and r[0]["id"] == "m1"
    check("C4 per-model dims coexist in one DB", ok_new and ok_old,
          f"new-384-dim ok={ok_new}, original-768 intact={ok_old}")

except Exception:
    traceback.print_exc()
    check("trial aborted", False)

print()
print(f"RESULT: {sum(1 for _, ok, _ in results if ok)}/{len(results)} passed  ({EMBEDDER_NAME})")
