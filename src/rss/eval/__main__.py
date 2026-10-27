import argparse

from rss import config, llm
from rss.db import connect
from rss.eval.ann import run_ann_benchmark
from rss.eval.core import (
    MODELS,
    ensure_embeddings,
    load_queries,
    relevant_ids,
    run_llm_experiment,
    run_search_experiment,
    sync_text_index,
)


def print_table(title: str, headers: list[str], rows: list[list]) -> None:
    widths = [max(len(str(x)) for x in col) for col in zip(headers, *rows)]
    print(f"\n{title}")
    print("  " + "  ".join(str(h).ljust(w) for h, w in zip(headers, widths)))
    for row in rows:
        print("  " + "  ".join(str(c).ljust(w) for c, w in zip(row, widths)))


def search_experiments(conn, queries) -> None:
    sync_text_index(conn)
    labels = {q["id"]: relevant_ids(conn, q["relevant"]) for q in queries}
    empty = [qid for qid, ids in labels.items() if not ids]
    if empty:
        raise SystemExit(f"queries without relevant restaurants: {empty}")
    print_table("Relevant restaurants per query", ["query", "relevant"], [[k, len(v)] for k, v in labels.items()])

    for model in MODELS:
        ensure_embeddings(conn, model)

    plan = [("A_models", m.split("/")[-1], m, "doc", None) for m in MODELS]
    plan += [("B_strategy", s, config.EMBEDDING_MODEL, s, None) for s in ("doc", "passage", "hybrid", "app")]
    if llm.status()["enabled"]:
        plan += [("C_llm", "llm text", config.EMBEDDING_MODEL, "app", "query"),
                 ("C_llm", "llm text + filters", config.EMBEDDING_MODEL, "app", "filters")]
    else:
        print("\nLLM disabled, skipping experiment C:", llm.status()["reason"])

    results = [run_search_experiment(conn, queries, labels, *p) for p in plan]
    print_table(
        "Search quality (k=10, averages over queries)",
        ["experiment", "variant", "P@10", "R@10", "MRR", "nDCG@10", "p50 ms"],
        [[r["experiment"], r["variant"], f"{r['precision']:.3f}", f"{r['recall']:.3f}", f"{r['mrr']:.3f}",
          f"{r['ndcg']:.3f}", f"{r['p50_ms']:.0f}"] for r in results],
    )
    languages = {q["id"]: ("pt" if q["id"].endswith("_pt") else "en") for q in queries}
    print_table(
        "nDCG@10 by question language",
        ["variant", "en", "pt"],
        [[r["variant"]] + [f"{_mean_ndcg(r['rows'], languages, lang):.3f}" for lang in ("en", "pt")] for r in results],
    )


def _mean_ndcg(rows: list[dict], languages: dict[str, str], lang: str) -> float:
    values = [x["ndcg"] for x in rows if languages[x["query_id"]] == lang]
    return sum(values) / max(1, len(values))


def llm_experiment(conn, queries) -> None:
    status = llm.status()
    if not status["enabled"]:
        print("\nLLM disabled, skipping filter evaluation:", status["reason"])
        return
    r = run_llm_experiment(conn, queries)
    print_table(
        f"AI filter extraction ({status['provider']}:{status['model']})",
        ["query", "ok", "semantic_query", "invented", "missed/wrong"],
        [[x["query_id"], "yes" if x["correct"] else "NO", x["semantic_query"][:40], ", ".join(x["invented"]),
          ", ".join(x["missed"] + x["wrong"])] for x in r["rows"]],
    )
    print(f"\n  fully correct: {r['accuracy']:.0%} · invented values: {r['invented']} · missed or wrong: {r['missed']}")


def ann_benchmark(conn, queries) -> None:
    results = run_ann_benchmark(conn, [q["question"] for q in queries])
    print_table(
        f"HNSW vs exact search on cur_review_passage ({results[0]['vectors']:,} vectors, k=10, {len(queries)} queries)",
        ["target accuracy", "recall vs exact", "exact p50/p95 ms", "approx p50/p95 ms", "plan"],
        [[r["target"], f"{r['recall']:.3f}", f"{r['exact_p50']:.1f} / {r['exact_p95']:.1f}",
          f"{r['approx_p50']:.1f} / {r['approx_p95']:.1f}", r["plan"]] for r in results],
    )


COMMANDS = {"search": search_experiments, "llm": llm_experiment, "ann": ann_benchmark}


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m rss.eval")
    parser.add_argument("commands", nargs="+", choices=list(COMMANDS))
    args = parser.parse_args()
    queries = load_queries()
    with connect() as conn:
        for command in args.commands:
            COMMANDS[command](conn, queries)


if __name__ == "__main__":
    main()
