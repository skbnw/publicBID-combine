"""Load the local research database into an initialized Supabase PostgreSQL project."""

from __future__ import annotations

import argparse
import os
import re
from pathlib import Path
from uuid import uuid4

import duckdb
import psycopg


ROOT = Path(__file__).resolve().parents[1]


def qname(schema: str, table: str) -> str:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", schema):
        raise ValueError(f"Invalid schema name: {schema}")
    return f"{schema}.{table}"


def copy_query(pg: psycopg.Connection, table: str, columns: list[str], rows) -> int:
    count = 0
    names = ", ".join(columns)
    with pg.cursor() as cursor, cursor.copy(f"COPY {table} ({names}) FROM STDIN") as copy:
        for row in rows:
            copy.write_row(row)
            count += 1
    return count


def main() -> None:
    parser = argparse.ArgumentParser(description="Upload DuckDB data to Supabase")
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL"))
    parser.add_argument("--schema", default=os.getenv("DB_SCHEMA", "procurement"))
    parser.add_argument("--local-db", type=Path, default=ROOT / "data" / "research.duckdb")
    parser.add_argument("--replace", action="store_true", help="Delete existing procurement and actor master data first")
    args = parser.parse_args()
    if not args.database_url:
        parser.error("Set DATABASE_URL or pass --database-url")

    local = duckdb.connect(str(args.local_db), read_only=True)
    pg = psycopg.connect(args.database_url, autocommit=False)
    try:
        schema = args.schema
        if args.replace:
            with pg.cursor() as cursor:
                cursor.execute(f"TRUNCATE {qname(schema, 'procurements')}, {qname(schema, 'actor_aliases')}, {qname(schema, 'actors')} CASCADE")

        with pg.cursor() as cursor:
            cursor.execute(f"CREATE TEMP TABLE load_actors (LIKE {qname(schema, 'actors')} INCLUDING DEFAULTS) ON COMMIT DROP")
            cursor.execute("CREATE TEMP TABLE load_aliases (actor_id text, alias text, source_type text) ON COMMIT DROP")
            cursor.execute(
                """
                CREATE TEMP TABLE load_procurements (
                  record_id text,
                  procurement_title text,
                  contract_date date,
                  award_amount_yen bigint,
                  fiscal_year integer,
                  ordering_body_code text,
                  ordering_body_name text,
                  vendor_actor_id text,
                  vendor_name_raw text,
                  vendor_name_canonical text,
                  corporation_number text,
                  ministry_name text,
                  reference_id text,
                  bidding_method_code text,
                  bidding_method_name text,
                  consulting_flag_strict boolean,
                  consulting_flag_broad boolean,
                  consulting_vendor_flag boolean,
                  consulting_categories text[],
                  consulting_vendor_category text,
                  tag_reason text,
                  exclusion_flag boolean,
                  duplicate_flag boolean,
                  source_file_name text,
                  source_row_number integer,
                  source_year integer,
                  analysis_included boolean
                ) ON COMMIT DROP
                """
            )

        actor_rows = local.execute(
            """
            SELECT actor_id,
                   any_value(actor_type) AS actor_type,
                   any_value(canonical_name) AS canonical_name,
                   CASE WHEN actor_id NOT LIKE 'vendor:%' THEN actor_id END AS corporation_number,
                   any_value(description) AS description,
                   NULL AS website_url
            FROM actors
            GROUP BY actor_id
            """
        ).fetchall()
        copy_query(pg, "load_actors", ["actor_id", "actor_type", "canonical_name", "corporation_number", "description", "website_url"], actor_rows)
        with pg.cursor() as cursor:
            cursor.execute(
                f"""
                INSERT INTO {qname(schema, 'actors')}(actor_id, actor_type, canonical_name, corporation_number, description, website_url)
                SELECT actor_id, actor_type, canonical_name, corporation_number, description, website_url
                FROM load_actors
                ON CONFLICT(actor_id) DO UPDATE SET canonical_name=excluded.canonical_name,
                  corporation_number=excluded.corporation_number, updated_at=now()
                """
            )

        alias_rows = local.execute(
            """
            SELECT actor_id, alias, any_value(source_type) AS source_type
            FROM actor_aliases
            GROUP BY actor_id, alias
            """
        ).fetchall()
        copy_query(pg, "load_aliases", ["actor_id", "alias", "source_type"], alias_rows)
        with pg.cursor() as cursor:
            cursor.execute(
                f"""
                INSERT INTO {qname(schema, 'actor_aliases')}(actor_id, alias, source_type)
                SELECT actor_id, alias, source_type
                FROM load_aliases
                ON CONFLICT(actor_id, alias) DO UPDATE SET source_type=excluded.source_type
                """
            )

        procurement_rows = local.execute(
            """
            SELECT record_id, procurement_title, contract_date, award_amount_yen, fiscal_year,
                   ordering_body_code, ordering_body_name,
                   COALESCE(NULLIF(corporation_number, ''), 'vendor:' || md5(vendor_name_canonical)) AS vendor_actor_id,
                   vendor_name, vendor_name_canonical, corporation_number, ministry_name, reference_id,
                   bidding_method_code, bidding_method_name,
                   consulting_flag_strict, consulting_flag_broad, consulting_vendor_flag,
                   CASE WHEN COALESCE(consulting_categories, '') = '' THEN [] ELSE string_split(consulting_categories, '|') END,
                   consulting_vendor_category, tag_reason, exclusion_flag, duplicate_flag,
                   source_file_name, source_row_number, source_year, analysis_included
            FROM procurements
            WHERE COALESCE(vendor_name_canonical, '') <> ''
            """
        ).fetchall()
        procurement_columns = [
            "record_id", "procurement_title", "contract_date", "award_amount_yen", "fiscal_year",
            "ordering_body_code", "ordering_body_name", "vendor_actor_id", "vendor_name_raw",
            "vendor_name_canonical", "corporation_number", "ministry_name", "reference_id",
            "bidding_method_code", "bidding_method_name", "consulting_flag_strict", "consulting_flag_broad",
            "consulting_vendor_flag", "consulting_categories", "consulting_vendor_category", "tag_reason",
            "exclusion_flag", "duplicate_flag", "source_file_name", "source_row_number", "source_year", "analysis_included",
        ]
        copied = copy_query(pg, "load_procurements", procurement_columns, procurement_rows)
        with pg.cursor() as cursor:
            cursor.execute(
                f"""
                INSERT INTO {qname(schema, 'procurements')}({', '.join(procurement_columns)})
                SELECT {', '.join(procurement_columns)} FROM load_procurements
                ON CONFLICT(source_file_name, source_row_number) DO UPDATE SET
                  procurement_title=excluded.procurement_title, contract_date=excluded.contract_date,
                  award_amount_yen=excluded.award_amount_yen, vendor_actor_id=excluded.vendor_actor_id,
                  vendor_name_canonical=excluded.vendor_name_canonical, corporation_number=excluded.corporation_number,
                  consulting_flag_strict=excluded.consulting_flag_strict,
                  consulting_flag_broad=excluded.consulting_flag_broad,
                  consulting_categories=excluded.consulting_categories,
                  analysis_included=excluded.analysis_included
                """
            )
            cursor.execute(
                f"INSERT INTO {qname(schema, 'data_imports')}(import_id, source_name, imported_at, row_count, pipeline_version) VALUES (%s, %s, now(), %s, %s)",
                (str(uuid4()), "government_procurement_all.csv", copied, "research-db-v1"),
            )
        pg.commit()
        print(f"Uploaded {copied:,} procurements to Supabase")
    except Exception:
        pg.rollback()
        raise
    finally:
        local.close()
        pg.close()


if __name__ == "__main__":
    main()
