from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]


def load_builder():
    spec = importlib.util.spec_from_file_location("procurement_builder", ROOT / "code" / "build_consulting_dataset.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def main() -> None:
    parser = argparse.ArgumentParser(description="Build an HTML report for a fixed fiscal-year window.")
    parser.add_argument("--start-fy", type=int, required=True)
    parser.add_argument("--end-fy", type=int, required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    source = ROOT / "output" / "government_procurement_all.csv"
    data = pd.read_csv(source, encoding="utf-8-sig", low_memory=False)
    data = data[
        data["analysis_included"].eq(True)
        & data["fiscal_year"].between(args.start_fy, args.end_fy, inclusive="both")
    ].copy()
    consult = data[data["consulting_flag_broad"].eq(True)].copy()
    yearly = (consult.groupby("fiscal_year", dropna=True)
              .agg(contract_count=("record_id", "size"), award_amount_yen=("award_amount_yen", "sum")).reset_index())
    exploded = consult.assign(
        consulting_categories=consult["consulting_categories"].fillna("").replace("", "受注者名のみ").str.split("|")
    ).explode("consulting_categories")
    category = (exploded.groupby(["fiscal_year", "consulting_categories"], dropna=True)
                .agg(contract_count=("record_id", "size"), award_amount_yen=("award_amount_yen", "sum")).reset_index())
    builder = load_builder()
    target = ROOT / "output" / args.output
    builder.build_html(data, yearly, category, target)
    print(f"{args.start_fy}-{args.end_fy}: {len(data):,} all rows / {len(consult):,} consulting rows -> {target}")


if __name__ == "__main__":
    main()
