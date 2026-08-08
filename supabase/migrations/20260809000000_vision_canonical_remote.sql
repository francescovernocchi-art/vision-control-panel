-- =============================================================================
-- VISION Control Panel — CANONICAL Supabase schema (Agent-first)
-- Source of truth: VISION Agent remote contract (vis-ion)
-- Copied/adapted from: vis-ion/supabase/migrations/20260808_vision_remote_readonly.sql
-- Device identity: devices.device_id TEXT (= public code, e.g. VIS-TARANTO-01)
-- Command identity: commands.command_id UUID
-- Remote policy: status_only — GET_STATUS only
-- DO NOT apply Lovable legacy migrations in supabase/migrations/legacy/
-- =============================================================================
-- VISâ€¢ION Remote â€” schema minimo READ-ONLY (GET_STATUS only)
-- api_version=v1 / contract_version=1.0.0
-- Applica su progetto Supabase dedicato. Reversibile: drop schema objects in coda commentata.
-- NON contiene secret. NON abilita comandi operativi.

create extension if not exists pgcrypto;

-- ---------------------------------------------------------------------------
-- Enums
-- ---------------------------------------------------------------------------
do $$ begin
  create type public.vision_device_status as enum ('ONLINE', 'DEGRADED', 'OFFLINE', 'DISABLED');
exception when duplicate_object then null; end $$;

do $$ begin
  create type public.vision_command_status as enum (
    'PENDING', 'ACKNOWLEDGED', 'EXECUTING', 'COMPLETED', 'FAILED', 'REJECTED'
  );
exception when duplicate_object then null; end $$;

do $$ begin
  create type public.vision_app_role as enum ('OPERATORE', 'ADMIN', 'DIREZIONE', 'AGENT');
exception when duplicate_object then null; end $$;

-- ---------------------------------------------------------------------------
-- Profiles (ruoli PWA)
-- ---------------------------------------------------------------------------
create table if not exists public.profiles (
  user_id uuid primary key references auth.users (id) on delete cascade,
  display_name text,
  role public.vision_app_role not null default 'OPERATORE',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- ---------------------------------------------------------------------------
-- Devices
-- ---------------------------------------------------------------------------
create table if not exists public.devices (
  device_id text primary key,
  device_name text not null,
  status public.vision_device_status not null default 'OFFLINE',
  agent_version text not null default '',
  vision_version text not null default '',
  platform_version text not null default '',
  last_seen_at timestamptz,
  current_job_id text,
  modules jsonb not null default '[]'::jsonb,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint devices_device_id_chk check (char_length(device_id) between 3 and 64)
);

create index if not exists idx_devices_last_seen on public.devices (last_seen_at desc);

-- ---------------------------------------------------------------------------
-- Heartbeats (append-only, leggeri)
-- ---------------------------------------------------------------------------
create table if not exists public.heartbeats (
  id bigserial primary key,
  device_id text not null references public.devices (device_id) on delete cascade,
  status text not null,
  agent_version text,
  vision_version text,
  platform_version text,
  current_job_id text,
  modules jsonb not null default '[]'::jsonb,
  recorded_at timestamptz not null default now(),
  payload jsonb not null default '{}'::jsonb
);

create index if not exists idx_heartbeats_device_time
  on public.heartbeats (device_id, recorded_at desc);

-- ---------------------------------------------------------------------------
-- Commands (solo GET_STATUS abilitato lato app / check constraint soft)
-- ---------------------------------------------------------------------------
create table if not exists public.commands (
  command_id uuid primary key default gen_random_uuid(),
  command_type text not null,
  module_id text not null default 'core',
  target_device_id text not null references public.devices (device_id) on delete cascade,
  parameters jsonb not null default '{}'::jsonb,
  requested_by uuid references auth.users (id) on delete set null,
  requested_at timestamptz not null default now(),
  expires_at timestamptz,
  status public.vision_command_status not null default 'PENDING',
  acknowledged_at timestamptz,
  started_at timestamptz,
  finished_at timestamptz,
  result jsonb,
  error text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint commands_type_whitelist_chk check (
    command_type in (
      'GET_STATUS',
      'CHECK_ENISPACE_MAIL',
      'RETRY_JOB',
      'PAUSE_MODULE',
      'RESUME_MODULE',
      'PREPARE_COIN_TRANSPORT',
      'APPROVE_JOB',
      'REJECT_JOB'
    )
  )
);

create index if not exists idx_commands_device_status
  on public.commands (target_device_id, status, requested_at desc);

create index if not exists idx_commands_pending
  on public.commands (target_device_id, requested_at)
  where status = 'PENDING';

-- Trigger: in fase status_only, blocca INSERT di comandi != GET_STATUS da utenti umani
create or replace function public.enforce_status_only_commands()
returns trigger
language plpgsql
as $$
declare
  v_role public.vision_app_role;
begin
  -- Agent technical updates (status transitions) sono UPDATE, non bloccati qui.
  if tg_op = 'INSERT' then
    if new.command_type <> 'GET_STATUS' then
      raise exception 'REMOTE_OPERATION_NOT_ENABLED: solo GET_STATUS consentito in questa fase'
        using errcode = '42501';
    end if;
    if new.module_id is null or new.module_id = '' then
      new.module_id := 'core';
    end if;
    if new.expires_at is null then
      new.expires_at := now() + interval '2 minutes';
    end if;
  end if;
  new.updated_at := now();
  return new;
end;
$$;

drop trigger if exists trg_commands_status_only on public.commands;
create trigger trg_commands_status_only
before insert or update on public.commands
for each row execute function public.enforce_status_only_commands();

-- ---------------------------------------------------------------------------
-- Agent sessions / token dedicato (hash, mai plaintext)
-- ---------------------------------------------------------------------------
create table if not exists public.agent_api_tokens (
  id uuid primary key default gen_random_uuid(),
  device_id text not null references public.devices (device_id) on delete cascade,
  token_hash text not null,
  label text not null default 'default',
  created_at timestamptz not null default now(),
  revoked_at timestamptz,
  last_used_at timestamptz,
  unique (device_id, label)
);

create table if not exists public.agent_sessions (
  id uuid primary key default gen_random_uuid(),
  device_id text not null references public.devices (device_id) on delete cascade,
  auth_user_id uuid references auth.users (id) on delete set null,
  started_at timestamptz not null default now(),
  last_seen_at timestamptz not null default now(),
  remote_mode text not null default 'supabase',
  metadata jsonb not null default '{}'::jsonb
);

-- ---------------------------------------------------------------------------
-- User â†” device authorization
-- ---------------------------------------------------------------------------
create table if not exists public.user_devices (
  user_id uuid not null references auth.users (id) on delete cascade,
  device_id text not null references public.devices (device_id) on delete cascade,
  can_command boolean not null default true,
  created_at timestamptz not null default now(),
  primary key (user_id, device_id)
);

-- ---------------------------------------------------------------------------
-- Audit minimo
-- ---------------------------------------------------------------------------
create table if not exists public.audit_logs (
  id bigserial primary key,
  actor_user_id uuid references auth.users (id) on delete set null,
  device_id text,
  action text not null,
  command_id uuid,
  command_type text,
  result_status text,
  detail jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists idx_audit_created on public.audit_logs (created_at desc);

-- ---------------------------------------------------------------------------
-- Seed device VIS-TARANTO-01
-- ---------------------------------------------------------------------------
insert into public.devices (device_id, device_name, status, metadata)
values (
  'VIS-TARANTO-01',
  'PC VIS Taranto',
  'OFFLINE',
  jsonb_build_object('offline_threshold_seconds', 60, 'remote_policy', 'status_only')
)
on conflict (device_id) do nothing;

-- ---------------------------------------------------------------------------
-- Helpers: ruolo corrente / device access
-- ---------------------------------------------------------------------------
create or replace function public.current_app_role()
returns public.vision_app_role
language sql
stable
security definer
set search_path = public, pg_temp
as $$
  select coalesce(
    (select role from public.profiles where user_id = auth.uid()),
    'OPERATORE'::public.vision_app_role
  );
$$;

create or replace function public.is_agent_user()
returns boolean
language sql
stable
security definer
set search_path = public, pg_temp
as $$
  select exists (
    select 1 from public.profiles
    where user_id = auth.uid() and role = 'AGENT'
  );
$$;

create or replace function public.user_can_read_device(p_device_id text)
returns boolean
language sql
stable
security definer
set search_path = public, pg_temp
as $$
  select
    auth.uid() is not null
    and (
      public.current_app_role() in ('ADMIN', 'AGENT')
      or exists (
        select 1 from public.user_devices ud
        where ud.user_id = auth.uid() and ud.device_id = p_device_id
      )
    );
$$;

create or replace function public.user_can_command_device(p_device_id text)
returns boolean
language sql
stable
security definer
set search_path = public, pg_temp
as $$
  select
    auth.uid() is not null
    and public.current_app_role() in ('OPERATORE', 'ADMIN')
    and (
      public.current_app_role() = 'ADMIN'
      or exists (
        select 1 from public.user_devices ud
        where ud.user_id = auth.uid()
          and ud.device_id = p_device_id
          and ud.can_command = true
      )
    );
$$;

-- Offline detection (backend-side view) â€” soglia da metadata.offline_threshold_seconds
create or replace view public.devices_with_derived_status as
select
  d.*,
  case
    when d.status = 'DISABLED' then 'DISABLED'
    when d.last_seen_at is null then 'OFFLINE'
    when now() - d.last_seen_at >
      make_interval(secs => coalesce((d.metadata->>'offline_threshold_seconds')::int, 60))
      then 'OFFLINE'
    else d.status::text
  end as derived_status
from public.devices d;

-- ---------------------------------------------------------------------------
-- RPC Agent: heartbeat (token dedicato SHA-256 hex o utente AGENT)
-- Token: encode(digest(raw_token, 'sha256'), 'hex')
-- ---------------------------------------------------------------------------
create or replace function public.agent_heartbeat(
  p_device_id text,
  p_agent_token text,
  p_status text,
  p_agent_version text default '',
  p_vision_version text default '',
  p_platform_version text default '',
  p_current_job_id text default '',
  p_modules jsonb default '[]'::jsonb,
  p_timestamp timestamptz default now()
)
returns jsonb
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
  v_hash text;
  v_ok boolean := false;
begin
  if p_agent_token is null or length(trim(p_agent_token)) < 16 then
    raise exception 'agent auth failed: token missing/short' using errcode = '42501';
  end if;
  v_hash := encode(digest(p_agent_token, 'sha256'), 'hex');

  if public.is_agent_user() then
    v_ok := true;
  elsif exists (
    select 1 from public.agent_api_tokens t
    where t.device_id = p_device_id
      and t.token_hash = v_hash
      and t.revoked_at is null
  ) then
    v_ok := true;
    update public.agent_api_tokens
      set last_used_at = now()
      where device_id = p_device_id and token_hash = v_hash and revoked_at is null;
  end if;

  if not v_ok then
    raise exception 'agent auth failed' using errcode = '42501';
  end if;

  -- Agent non scrive OFFLINE
  if upper(p_status) = 'OFFLINE' then
    p_status := 'DEGRADED';
  end if;

  insert into public.devices as d (
    device_id, device_name, status, agent_version, vision_version, platform_version,
    last_seen_at, current_job_id, modules, updated_at
  ) values (
    p_device_id,
    coalesce((select device_name from public.devices where device_id = p_device_id), p_device_id),
    p_status::public.vision_device_status,
    coalesce(p_agent_version, ''),
    coalesce(p_vision_version, ''),
    coalesce(p_platform_version, ''),
    coalesce(p_timestamp, now()),
    nullif(p_current_job_id, ''),
    coalesce(p_modules, '[]'::jsonb),
    now()
  )
  on conflict (device_id) do update set
    status = excluded.status,
    agent_version = excluded.agent_version,
    vision_version = excluded.vision_version,
    platform_version = excluded.platform_version,
    last_seen_at = excluded.last_seen_at,
    current_job_id = excluded.current_job_id,
    modules = excluded.modules,
    updated_at = now();

  insert into public.heartbeats (
    device_id, status, agent_version, vision_version, platform_version,
    current_job_id, modules, recorded_at, payload
  ) values (
    p_device_id, p_status, p_agent_version, p_vision_version, p_platform_version,
    nullif(p_current_job_id, ''), coalesce(p_modules, '[]'::jsonb), coalesce(p_timestamp, now()),
    jsonb_build_object('source', 'agent_heartbeat')
  );

  insert into public.agent_sessions (device_id, last_seen_at, remote_mode)
  values (p_device_id, coalesce(p_timestamp, now()), 'supabase');

  return jsonb_build_object('ok', true, 'device_id', p_device_id, 'status', p_status);
end;
$$;

create or replace function public.agent_fetch_pending_commands(
  p_device_id text,
  p_agent_token text,
  p_limit int default 10
)
returns setof public.commands
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
  v_hash text;
  v_ok boolean := false;
begin
  if p_agent_token is null or length(trim(p_agent_token)) < 16 then
    raise exception 'agent auth failed: token missing/short' using errcode = '42501';
  end if;
  v_hash := encode(digest(p_agent_token, 'sha256'), 'hex');
  if public.is_agent_user() then
    v_ok := true;
  elsif exists (
    select 1 from public.agent_api_tokens t
    where t.device_id = p_device_id and t.token_hash = v_hash and t.revoked_at is null
  ) then
    v_ok := true;
  end if;
  if not v_ok then
    raise exception 'agent auth failed' using errcode = '42501';
  end if;

  return query
  select c.*
  from public.commands c
  where c.target_device_id = p_device_id
    and c.status = 'PENDING'
    and (c.expires_at is null or c.expires_at > now())
  order by c.requested_at asc
  limit greatest(1, least(coalesce(p_limit, 10), 50));
end;
$$;

create or replace function public.agent_update_command(
  p_device_id text,
  p_agent_token text,
  p_command_id uuid,
  p_status text,
  p_result jsonb default null,
  p_error text default null,
  p_acknowledged_at timestamptz default null,
  p_started_at timestamptz default null,
  p_finished_at timestamptz default null
)
returns jsonb
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
  v_hash text;
  v_ok boolean := false;
  v_row public.commands;
begin
  if p_agent_token is null or length(trim(p_agent_token)) < 16 then
    raise exception 'agent auth failed: token missing/short' using errcode = '42501';
  end if;
  v_hash := encode(digest(p_agent_token, 'sha256'), 'hex');
  if public.is_agent_user() then
    v_ok := true;
  elsif exists (
    select 1 from public.agent_api_tokens t
    where t.device_id = p_device_id and t.token_hash = v_hash and t.revoked_at is null
  ) then
    v_ok := true;
  end if;
  if not v_ok then
    raise exception 'agent auth failed' using errcode = '42501';
  end if;

  update public.commands c
  set
    status = p_status::public.vision_command_status,
    result = coalesce(p_result, c.result),
    error = coalesce(p_error, c.error),
    acknowledged_at = coalesce(p_acknowledged_at, c.acknowledged_at),
    started_at = coalesce(p_started_at, c.started_at),
    finished_at = coalesce(p_finished_at, c.finished_at),
    updated_at = now()
  where c.command_id = p_command_id
    and c.target_device_id = p_device_id
  returning * into v_row;

  if v_row.command_id is null then
    raise exception 'command not found' using errcode = 'P0002';
  end if;

  return to_jsonb(v_row);
end;
$$;

-- PWA: crea GET_STATUS + audit
create or replace function public.create_get_status_command(p_device_id text)
returns public.commands
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
  v_cmd public.commands;
begin
  if auth.uid() is null then
    raise exception 'not authenticated' using errcode = '42501';
  end if;
  if public.current_app_role() = 'DIREZIONE' then
    raise exception 'DIREZIONE cannot create commands' using errcode = '42501';
  end if;
  if not public.user_can_command_device(p_device_id) then
    raise exception 'device not authorized' using errcode = '42501';
  end if;

  insert into public.commands (
    command_type, module_id, target_device_id, parameters,
    requested_by, requested_at, expires_at, status
  ) values (
    'GET_STATUS', 'core', p_device_id, '{}'::jsonb,
    auth.uid(), now(), now() + interval '2 minutes', 'PENDING'
  )
  returning * into v_cmd;

  insert into public.audit_logs (
    actor_user_id, device_id, action, command_id, command_type, result_status, detail
  ) values (
    auth.uid(), p_device_id, 'CREATE_GET_STATUS', v_cmd.command_id, 'GET_STATUS', 'PENDING',
    jsonb_build_object('api_version', 'v1', 'contract_version', '1.0.0')
  );

  return v_cmd;
end;
$$;

-- ---------------------------------------------------------------------------
-- RLS
-- ---------------------------------------------------------------------------
alter table public.profiles enable row level security;
alter table public.devices enable row level security;
alter table public.heartbeats enable row level security;
alter table public.commands enable row level security;
alter table public.agent_api_tokens enable row level security;
alter table public.agent_sessions enable row level security;
alter table public.user_devices enable row level security;
alter table public.audit_logs enable row level security;

-- profiles
drop policy if exists profiles_select_own on public.profiles;
create policy profiles_select_own on public.profiles
  for select to authenticated
  using (user_id = auth.uid() or public.current_app_role() = 'ADMIN');

drop policy if exists profiles_update_own on public.profiles;
create policy profiles_update_own on public.profiles
  for update to authenticated
  using (user_id = auth.uid() or public.current_app_role() = 'ADMIN');

-- devices
drop policy if exists devices_select_authorized on public.devices;
create policy devices_select_authorized on public.devices
  for select to authenticated
  using (public.user_can_read_device(device_id) or public.is_agent_user());

drop policy if exists devices_update_agent on public.devices;
create policy devices_update_agent on public.devices
  for update to authenticated
  using (public.is_agent_user());

-- heartbeats: utenti leggono; insert solo via RPC agent (security definer)
drop policy if exists heartbeats_select_authorized on public.heartbeats;
create policy heartbeats_select_authorized on public.heartbeats
  for select to authenticated
  using (public.user_can_read_device(device_id) or public.is_agent_user());

-- commands
drop policy if exists commands_select_authorized on public.commands;
create policy commands_select_authorized on public.commands
  for select to authenticated
  using (
    public.user_can_read_device(target_device_id)
    or public.is_agent_user()
    or requested_by = auth.uid()
  );

-- Insert comandi solo via create_get_status_command (security definer) oppure OPERATORE diretto GET_STATUS
drop policy if exists commands_insert_operator on public.commands;
create policy commands_insert_operator on public.commands
  for insert to authenticated
  with check (
    command_type = 'GET_STATUS'
    and public.user_can_command_device(target_device_id)
  );

drop policy if exists commands_update_agent on public.commands;
create policy commands_update_agent on public.commands
  for update to authenticated
  using (public.is_agent_user() or public.current_app_role() = 'ADMIN');

-- tokens: solo ADMIN
drop policy if exists agent_tokens_admin on public.agent_api_tokens;
create policy agent_tokens_admin on public.agent_api_tokens
  for all to authenticated
  using (public.current_app_role() = 'ADMIN')
  with check (public.current_app_role() = 'ADMIN');

drop policy if exists agent_sessions_select on public.agent_sessions;
create policy agent_sessions_select on public.agent_sessions
  for select to authenticated
  using (public.user_can_read_device(device_id) or public.is_agent_user() or public.current_app_role() = 'ADMIN');

drop policy if exists user_devices_select on public.user_devices;
create policy user_devices_select on public.user_devices
  for select to authenticated
  using (user_id = auth.uid() or public.current_app_role() = 'ADMIN');

drop policy if exists user_devices_admin on public.user_devices;
create policy user_devices_admin on public.user_devices
  for all to authenticated
  using (public.current_app_role() = 'ADMIN')
  with check (public.current_app_role() = 'ADMIN');

drop policy if exists audit_select on public.audit_logs;
create policy audit_select on public.audit_logs
  for select to authenticated
  using (
    actor_user_id = auth.uid()
    or public.current_app_role() in ('ADMIN', 'DIREZIONE')
    or (device_id is not null and public.user_can_read_device(device_id))
  );

-- audit immutabile da client (insert solo via RPC security definer)
drop policy if exists audit_no_client_write on public.audit_logs;
create policy audit_no_client_write on public.audit_logs
  for insert to authenticated
  with check (false);

drop policy if exists audit_no_client_update on public.audit_logs;
create policy audit_no_client_update on public.audit_logs
  for update to authenticated
  using (false);

drop policy if exists audit_no_client_delete on public.audit_logs;
create policy audit_no_client_delete on public.audit_logs
  for delete to authenticated
  using (false);

-- Realtime publication
do $$ begin
  alter publication supabase_realtime add table public.commands;
exception when others then null; end $$;
do $$ begin
  alter publication supabase_realtime add table public.devices;
exception when others then null; end $$;

-- ---------------------------------------------------------------------------
-- Privileges: anon NON legge tabelle; solo RPC Agent con token
-- ---------------------------------------------------------------------------
revoke all on table public.profiles from anon, public;
revoke all on table public.devices from anon, public;
revoke all on table public.heartbeats from anon, public;
revoke all on table public.commands from anon, public;
revoke all on table public.agent_api_tokens from anon, public;
revoke all on table public.agent_sessions from anon, public;
revoke all on table public.user_devices from anon, public;
revoke all on table public.audit_logs from anon, public;

grant select on table public.profiles to authenticated;
grant select on table public.devices to authenticated;
grant select on table public.heartbeats to authenticated;
grant select, insert on table public.commands to authenticated;
grant select on table public.agent_sessions to authenticated;
grant select on table public.user_devices to authenticated;
grant select on table public.audit_logs to authenticated;
-- agent_api_tokens: nessun grant a authenticated generico; solo ADMIN via policy + table owner/service
grant select, insert, update, delete on table public.agent_api_tokens to authenticated;

-- audit: nessun insert/update/delete diretto (solo RPC security definer)
revoke insert, update, delete on table public.audit_logs from authenticated, anon, public;

-- heartbeats/devices write: solo via RPC Agent (security definer bypassa RLS come owner)
revoke insert, update, delete on table public.heartbeats from authenticated, anon, public;
revoke insert, delete on table public.devices from authenticated, anon, public;
-- update devices: solo role AGENT (JWT tecnico) se usato; token path usa RPC
grant update on table public.devices to authenticated;
grant update on table public.commands to authenticated;

-- Grants RPC: Agent usa anon key + VISION_AGENT_TOKEN arg; PWA autenticata per create_get_status
grant execute on function public.agent_heartbeat(
  text, text, text, text, text, text, text, jsonb, timestamptz
) to anon, authenticated;
grant execute on function public.agent_fetch_pending_commands(text, text, int)
  to anon, authenticated;
grant execute on function public.agent_update_command(
  text, text, uuid, text, jsonb, text, timestamptz, timestamptz, timestamptz
) to anon, authenticated;
grant execute on function public.create_get_status_command(text) to authenticated;
-- esplicito: niente grant service_role richiesto dal client Python

comment on function public.agent_heartbeat is
  'Auth Agent: VISION_AGENT_TOKEN (raw) hashed SHA-256 vs agent_api_tokens. No service_role in Python.';
comment on table public.commands is
  'Fase status_only: INSERT != GET_STATUS bloccato da trigger. Agent Python status_only.';
comment on table public.agent_api_tokens is
  'Solo ADMIN via RLS. Token raw mai in DB. Anon non ha privilegi tabella.';



