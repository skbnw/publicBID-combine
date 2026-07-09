"""Build the local research database from the normalized procurement CSV."""

from __future__ import annotations

import argparse
from pathlib import Path

import duckdb


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=ROOT / "output" / "government_procurement_all.csv")
    parser.add_argument("--output", type=Path, default=ROOT / "data" / "research.duckdb")
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect(str(args.output))
    source = str(args.input.resolve()).replace("'", "''")
    con.execute("DROP TABLE IF EXISTS procurements")
    con.execute(
        f"""
        CREATE TABLE procurements AS
        SELECT
            CAST(record_id AS VARCHAR) AS record_id,
            procurement_title,
            TRY_CAST(contract_date AS DATE) AS contract_date,
            TRY_CAST(award_amount_yen AS BIGINT) AS award_amount_yen,
            ministry_code, ministry_name,
            bidding_method_code, bidding_method_name,
            vendor_name, vendor_name_canonical,
            corporation_number,
            ordering_body_code, ordering_body_name,
            reference_id,
            TRY_CAST(source_year AS INTEGER) AS source_year,
            TRY_CAST(fiscal_year AS INTEGER) AS fiscal_year,
            TRY_CAST(consulting_flag_strict AS BOOLEAN) AS consulting_flag_strict,
            TRY_CAST(consulting_flag_broad AS BOOLEAN) AS consulting_flag_broad,
            TRY_CAST(consulting_vendor_flag AS BOOLEAN) AS consulting_vendor_flag,
            consulting_categories, consulting_vendor_category,
            tag_reason,
            TRY_CAST(exclusion_flag AS BOOLEAN) AS exclusion_flag,
            TRY_CAST(duplicate_flag AS BOOLEAN) AS duplicate_flag,
            TRY_CAST(analysis_included AS BOOLEAN) AS analysis_included,
            source_file_name,
            TRY_CAST(source_row_number AS INTEGER) AS source_row_number
        FROM read_csv_auto('{source}', header=true, all_varchar=true, ignore_errors=true)
        """
    )
    con.execute("CREATE INDEX procurement_fy_idx ON procurements(fiscal_year)")
    con.execute("CREATE INDEX procurement_vendor_idx ON procurements(vendor_name_canonical)")
    con.execute("CREATE INDEX procurement_body_idx ON procurements(ordering_body_name)")

    con.execute("DROP TABLE IF EXISTS actors")
    con.execute(
        """
        CREATE TABLE actors AS
        SELECT
            COALESCE(NULLIF(corporation_number, ''), 'vendor:' || md5(vendor_name_canonical)) AS actor_id,
            'organization' AS actor_type,
            vendor_name_canonical AS canonical_name,
            NULL::VARCHAR AS description,
            COUNT(*) AS procurement_count,
            SUM(award_amount_yen) AS award_amount_yen,
            MIN(fiscal_year) AS first_fiscal_year,
            MAX(fiscal_year) AS last_fiscal_year
        FROM procurements
        WHERE analysis_included AND COALESCE(vendor_name_canonical, '') <> ''
        GROUP BY ALL
        """
    )
    con.execute("DROP TABLE IF EXISTS actor_aliases")
    con.execute(
        """
        CREATE TABLE actor_aliases AS
        SELECT DISTINCT
            COALESCE(NULLIF(corporation_number, ''), 'vendor:' || md5(vendor_name_canonical)) AS actor_id,
            vendor_name AS alias,
            'procurement_record' AS source_type
        FROM procurements
        WHERE COALESCE(vendor_name, '') <> '' AND COALESCE(vendor_name_canonical, '') <> ''
        """
    )
    con.execute("CREATE TABLE IF NOT EXISTS actor_relations (relation_id VARCHAR, source_actor_id VARCHAR, target_actor_id VARCHAR, relation_type VARCHAR, start_date DATE, end_date DATE, evidence_url VARCHAR, note VARCHAR, created_by VARCHAR, created_at TIMESTAMP)")
    con.execute("CREATE TABLE IF NOT EXISTS annotations (annotation_id VARCHAR, target_type VARCHAR, target_id VARCHAR, body VARCHAR, evidence_url VARCHAR, status VARCHAR, created_by VARCHAR, created_at TIMESTAMP, updated_at TIMESTAMP)")
    con.execute("CREATE TABLE IF NOT EXISTS data_imports (import_id VARCHAR, source_name VARCHAR, source_url VARCHAR, source_year INTEGER, imported_at TIMESTAMP, row_count BIGINT, pipeline_version VARCHAR)")
    count = con.execute("SELECT COUNT(*) FROM procurements").fetchone()[0]
    actors = con.execute("SELECT COUNT(*) FROM actors").fetchone()[0]
    con.close()
    print(f"Built {args.output}: {count:,} procurements / {actors:,} actors")


if __name__ == "__main__":
    main()
