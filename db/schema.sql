-- PostgreSQL / Supabase production schema for the polidata project.
-- Raw imports remain immutable; researcher-authored information is stored
-- separately with provenance.

create schema if not exists procurement;

create table if not exists procurement.actors (
  actor_id text primary key,
  actor_type text not null check (actor_type in ('organization','government','person','other')),
  canonical_name text not null,
  corporation_number text,
  description text,
  website_url text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists procurement_actors_name_idx on procurement.actors using gin (to_tsvector('simple', canonical_name));

create table if not exists procurement.actor_aliases (
  alias_id bigint generated always as identity primary key,
  actor_id text not null references procurement.actors(actor_id),
  alias text not null,
  source_type text,
  unique(actor_id, alias)
);

create table if not exists procurement.procurements (
  procurement_id bigint generated always as identity primary key,
  record_id text,
  procurement_title text,
  contract_date date,
  award_amount_yen bigint,
  fiscal_year integer,
  ordering_body_code text,
  ordering_body_name text,
  vendor_actor_id text references procurement.actors(actor_id),
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
  analysis_included boolean not null default true,
  unique(source_file_name, source_row_number)
);
create index if not exists procurement_procurements_fy_idx on procurement.procurements(fiscal_year);
create index if not exists procurement_procurements_vendor_idx on procurement.procurements(vendor_actor_id);
create index if not exists procurement_procurements_vendor_name_idx on procurement.procurements(vendor_name_canonical);
create index if not exists procurement_procurements_body_idx on procurement.procurements(ordering_body_name);
create index if not exists procurement_procurements_bidding_method_idx on procurement.procurements(bidding_method_name);
create index if not exists procurement_procurements_title_idx on procurement.procurements using gin (to_tsvector('simple', procurement_title));

create table if not exists procurement.actor_relations (
  relation_id uuid primary key default gen_random_uuid(),
  source_actor_id text not null references procurement.actors(actor_id),
  target_actor_id text not null references procurement.actors(actor_id),
  relation_type text not null,
  start_date date,
  end_date date,
  evidence_url text,
  note text,
  created_by uuid references auth.users(id),
  created_at timestamptz not null default now()
);

create table if not exists procurement.annotations (
  annotation_id uuid primary key default gen_random_uuid(),
  target_type text not null,
  target_id text not null,
  body text not null,
  evidence_url text,
  status text not null default 'draft' check (status in ('draft','reviewed','disputed')),
  created_by uuid references auth.users(id),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists procurement.data_imports (
  import_id uuid primary key default gen_random_uuid(),
  source_name text not null,
  source_url text,
  source_year integer,
  imported_at timestamptz not null default now(),
  row_count bigint,
  pipeline_version text
);

alter table procurement.actors enable row level security;
alter table procurement.actor_aliases enable row level security;
alter table procurement.procurements enable row level security;
alter table procurement.actor_relations enable row level security;
alter table procurement.annotations enable row level security;
alter table procurement.data_imports enable row level security;

-- Optional read-only role for Streamlit Community Cloud.
-- After running this file, set a strong password manually in Supabase SQL Editor:
--   alter role procurement_reader with password 'REPLACE_WITH_STRONG_PASSWORD';
do $$
begin
  if not exists (select 1 from pg_roles where rolname = 'procurement_reader') then
    create role procurement_reader login;
  end if;
end $$;

-- Read policies for Supabase Auth/API clients.
-- The Streamlit app should preferably use a read-only PostgreSQL role via DATABASE_URL.
create policy "authenticated read actors" on procurement.actors for select to authenticated using (true);
create policy "authenticated read aliases" on procurement.actor_aliases for select to authenticated using (true);
create policy "authenticated read procurements" on procurement.procurements for select to authenticated using (true);
create policy "authenticated read relations" on procurement.actor_relations for select to authenticated using (true);
create policy "authenticated insert relations" on procurement.actor_relations for insert to authenticated with check (created_by = auth.uid());
create policy "authenticated read annotations" on procurement.annotations for select to authenticated using (true);
create policy "authors manage annotations" on procurement.annotations for all to authenticated using (created_by = auth.uid()) with check (created_by = auth.uid());
create policy "authenticated read imports" on procurement.data_imports for select to authenticated using (true);

-- Read policies for direct PostgreSQL connections from Streamlit Community Cloud.
create policy "reader read actors" on procurement.actors for select to procurement_reader using (true);
create policy "reader read aliases" on procurement.actor_aliases for select to procurement_reader using (true);
create policy "reader read procurements" on procurement.procurements for select to procurement_reader using (true);
create policy "reader read relations" on procurement.actor_relations for select to procurement_reader using (true);
create policy "reader read annotations" on procurement.annotations for select to procurement_reader using (true);
create policy "reader read imports" on procurement.data_imports for select to procurement_reader using (true);

grant usage on schema procurement to procurement_reader;
grant select on all tables in schema procurement to procurement_reader;
alter default privileges in schema procurement grant select on tables to procurement_reader;
