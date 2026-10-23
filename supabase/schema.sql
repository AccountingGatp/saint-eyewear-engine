-- Reproducible schema for operator review. Do not run blindly over unrelated apps.
-- The corresponding workspace migration was already applied to the Saint project.
create table if not exists public.runs (
 id uuid primary key default gen_random_uuid(),
 owner_id uuid not null references auth.users(id), report_month date not null,
 status text not null default 'uploaded' check(status in ('uploaded','blocked','review','ready','generated','error')),
 source_paths jsonb not null default '{}'::jsonb, figures jsonb not null default '{}'::jsonb,
 flags jsonb not null default '[]'::jsonb, notes jsonb not null default '{}'::jsonb,
 result_paths jsonb not null default '{}'::jsonb, reviewed_by text, reviewed_at timestamptz,
 error_message text, created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
alter table public.runs add column if not exists version integer not null default 1;
alter table public.runs add column if not exists config_snapshot jsonb not null default '{}'::jsonb;
alter table public.runs add column if not exists reviewed_user_id uuid references auth.users(id);
alter table public.runs add column if not exists source_expired boolean not null default false;
alter table public.runs add column if not exists processing_until timestamptz;
create table if not exists public.saint_members (
 email text primary key check(email=lower(email)),
 role text not null check(role in ('staff','reviewer','team_leader')),
 active boolean not null default true, created_at timestamptz not null default now()
);
create table if not exists public.saint_settings (
 id integer primary key check(id=1), config jsonb not null default '{}'::jsonb,
 retention_confirmed boolean not null default false, updated_at timestamptz not null default now()
);
create table if not exists public.saint_issued (
 id uuid primary key default gen_random_uuid(), report_month date not null,
 figures jsonb not null, source_description text not null,
 created_by uuid not null references auth.users(id), created_at timestamptz not null default now()
);
create table if not exists public.saint_artifacts (
 id uuid primary key default gen_random_uuid(),run_id uuid not null references public.runs(id) on delete cascade,
 kind text not null,path text not null unique,filename text not null,created_at timestamptz not null default now()
);
create table if not exists public.saint_audit (
 id bigint generated always as identity primary key,run_id uuid,actor_id uuid,event text not null,
 created_at timestamptz not null default now()
);
create index if not exists saint_issued_month_idx on public.saint_issued(report_month,created_at desc);
create index if not exists saint_artifacts_run_idx on public.saint_artifacts(run_id);
alter table public.runs enable row level security;
alter table public.saint_members enable row level security;
alter table public.saint_settings enable row level security;
alter table public.saint_issued enable row level security;
alter table public.saint_artifacts enable row level security;
alter table public.saint_audit enable row level security;
revoke all on public.runs,public.saint_members,public.saint_settings,public.saint_issued,public.saint_artifacts,public.saint_audit from anon,authenticated;
revoke update(source_paths,notes,reviewed_by,reviewed_at) on public.runs from authenticated;
grant select on public.runs,public.saint_members to authenticated;
grant all on public.runs,public.saint_members,public.saint_settings,public.saint_issued,public.saint_artifacts,public.saint_audit to service_role;
grant usage,select on sequence public.saint_audit_id_seq to service_role;
drop policy if exists "read own membership" on public.saint_members;
create policy "read own membership" on public.saint_members for select to authenticated
 using(email=lower((select auth.jwt()->>'email')));
drop policy if exists "owners read runs" on public.runs;
drop policy if exists "owners create runs" on public.runs;
drop policy if exists "owners update runs" on public.runs;
drop policy if exists "owners delete runs" on public.runs;
drop policy if exists "authorized team read runs" on public.runs;
create policy "authorized team read runs" on public.runs for select to authenticated using(
 exists(select 1 from public.saint_members m where m.email=lower((select auth.jwt()->>'email')) and m.active
 and (m.role in ('reviewer','team_leader') or runs.owner_id=(select auth.uid())))
);
insert into public.saint_members(email,role) values('accounting@gatpsolutions.com','team_leader') on conflict(email) do nothing;
insert into public.saint_settings(id) values(1) on conflict do nothing;
insert into storage.buckets(id,name,public,file_size_limit) values('saint-private','saint-private',false,25000000)
 on conflict(id) do update set public=false,file_size_limit=25000000;
drop policy if exists "users upload their source files" on storage.objects;
drop policy if exists "users read their own private files" on storage.objects;
-- No client policies on server-only tables or private objects: signed links are issued server-side.
