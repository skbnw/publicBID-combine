-- Run this once in Supabase SQL Editor if Streamlit Cloud connects but sees no rows.
-- It allows the direct PostgreSQL login role used by Streamlit Community Cloud
-- to read tables protected by Row Level Security.

grant usage on schema procurement to procurement_reader;
grant select on all tables in schema procurement to procurement_reader;

drop policy if exists "reader read actors" on procurement.actors;
drop policy if exists "reader read aliases" on procurement.actor_aliases;
drop policy if exists "reader read procurements" on procurement.procurements;
drop policy if exists "reader read relations" on procurement.actor_relations;
drop policy if exists "reader read annotations" on procurement.annotations;
drop policy if exists "reader read imports" on procurement.data_imports;

create policy "reader read actors" on procurement.actors for select to procurement_reader using (true);
create policy "reader read aliases" on procurement.actor_aliases for select to procurement_reader using (true);
create policy "reader read procurements" on procurement.procurements for select to procurement_reader using (true);
create policy "reader read relations" on procurement.actor_relations for select to procurement_reader using (true);
create policy "reader read annotations" on procurement.annotations for select to procurement_reader using (true);
create policy "reader read imports" on procurement.data_imports for select to procurement_reader using (true);
