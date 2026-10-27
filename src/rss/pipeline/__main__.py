import argparse
import time

from rss import config
from rss.db import connect, run_sql_file
from rss.pipeline.docs import build_docs
from rss.pipeline.embed import embed
from rss.pipeline.load_raw import load_business, load_reviews
from rss.pipeline.migrate import migrate
from rss.pipeline.passages import embed_passages
from rss.pipeline.quality import run_checks


def transform(name: str):
    return lambda conn: run_sql_file(conn, config.DB_DIR / "transform" / f"{name}.sql")


STEPS = {
    "migrate": migrate,
    "load-business": load_business,
    "stg-business": transform("stg_business"),
    "load-reviews": load_reviews,
    "stg-review": transform("stg_review"),
    "dq": run_checks,
    "curated": transform("curated"),
    "docs": build_docs,
    "embed": embed,
    "passages": embed_passages,
}


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m rss.pipeline")
    parser.add_argument("steps", nargs="+", choices=[*STEPS, "all"])
    parser.add_argument("--model", help="embedding model for the embed and passages steps")
    args = parser.parse_args()
    if args.model:
        config.EMBEDDING_MODEL = args.model
    steps = list(STEPS) if "all" in args.steps else args.steps

    with connect() as conn:
        for step in steps:
            t0 = time.time()
            print(f"== {step}")
            STEPS[step](conn)
            print(f"   done in {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
