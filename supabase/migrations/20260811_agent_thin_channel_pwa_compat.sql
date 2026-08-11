-- VIS•ION Agent — thin channel (PWA-compatible, additive)
-- Contract: docs/VISION_CP_AGENT_THIN_CHANNEL.md
--
-- Scope: heartbeat + WAKE_SUPERVISOR / DEACTIVATE_SUPERVISOR / GET_STATUS + optional messages.
-- Does NOT DROP public.devices. Does NOT replace PWA columns (id/code/name/…).
-- Safe to re-run (IF NOT EXISTS / OR REPLACE / guarded ALTERs).
--
-- Live PWA shape (observed): devices(id uuid, code, name, status, …) WITHOUT device_id.
-- Agent logical id = text (VISION_DEVICE_ID), stored in devices.device_id (+ synced to code).

create extension if not exists pgcrypto;

-- ---------------------------------------------------------------------------
-- devices: add Agent contract columns (preserve PWA id/code/name/…)
-- ---------------------------------------------------------------------------
alter table public.devices add column if not exists device_id text;
alter table public.devices add column if not exists vision_version text not null default '';
alter table public.devices add column if not exists platform_version text not null default '';
alter table public.devices add column if not exists modules jsonb not null default '[]'::jsonb;

-- Backfill logical id from PWA code (or name) — never wipe existing rows
update public.devices
set device_id = coalesce(nullif(trim(device_id), ''), nullif(trim(code), ''), nullif(trim(name), ''), id::text)
where device_id is null or trim(device_id) = '';

-- Unique index for Agent upserts (nullable rows skipped until backfilled)
create unique index if not exists uq_devices_device_id
  on public.devices (device_id)
  where device_id is not null and length(trim(device_id)) > 0;

do $$
begin
  if not exists (
    select 1 from pg_constraint where conname = 'devices_device_id_chk'
  ) then
    alter table public.devices
      add constraint devices_device_id_chk
      check (device_id is null or char_length(device_id) between 3 and 64);
  end if;
exception when others then
  raise notice 'devices_device_id_chk skipped: %', sqlerrm;
end $$;

-- Keep code in sync when present (PWA uses code)
update public.devices
set code = device_id
where device_id is not null
  and (code is null or trim(code) = '' or code <> device_id);

-- Seed Agent device if missing (status/metadata types vary on PWA — best-effort)
do $$
begin
  if not exists (
    select 1 from public.devices d
    where d.device_id = 'VIS-TARANTO-01' or d.code = 'VIS-TARANTO-01'
  ) then
    begin
      insert into public.devices (id, code, device_id, name, status, metadata)
      values (
        gen_random_uuid(),
        'VIS-TARANTO-01',
        'VIS-TARANTO-01',
        'PC VIS Taranto',
        'OFFLINE',
        jsonb_build_object('remote_policy', 'thin_channel', 'offline_threshold_seconds', 60)
      );
    exception when others then
      -- fallback senza metadata / status custom
      begin
        insert into public.devices (id, code, device_id, name)
        values (
          gen_random_uuid(),
          'VIS-TARANTO-01',
          'VIS-TARANTO-01',
          'PC VIS Taranto'
        );
      exception when others then
        raise notice 'seed VIS-TARANTO-01 skipped: %', sqlerrm;
      end;
    end;
  end if;
end $$;

-- ---------------------------------------------------------------------------
-- commands: lifecycle columns Agent expects (PWA may use id as PK)
-- ---------------------------------------------------------------------------
alter table public.commands add column if not exists expires_at timestamptz;
alter table public.commands add column if not exists acknowledged_at timestamptz;
alter table public.commands add column if not exists started_at timestamptz;
alter table public.commands add column if not exists finished_at timestamptz;
alter table public.commands add column if not exists updated_at timestamptz default now();
alter table public.commands add column if not exists created_at timestamptz default now();

-- Soft default expiry for new pending rows (trigger below)
create or replace function public.vision_thin_commands_defaults()
returns trigger
language plpgsql
as $$
begin
  if tg_op = 'INSERT' then
    if new.expires_at is null then
      new.expires_at := now() + interval '5 minutes';
    end if;
    if new.created_at is null then
      new.created_at := now();
    end if;
  end if;
  new.updated_at := now();
  return new;
end;
$$;

drop trigger if exists trg_vision_thin_commands_defaults on public.commands;
create trigger trg_vision_thin_commands_defaults
before insert or update on public.commands
for each row execute function public.vision_thin_commands_defaults();

create index if not exists idx_commands_target_status_requested
  on public.commands (target_device_id, status, requested_at desc);

-- ---------------------------------------------------------------------------
-- heartbeats (append-only) — device_id TEXT = logical Agent id
-- ---------------------------------------------------------------------------
create table if not exists public.heartbeats (
  id bigserial primary key,
  device_id text not null,
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
-- agent_api_tokens / agent_sessions / agent_messages (thin)
-- ---------------------------------------------------------------------------
create table if not exists public.agent_api_tokens (
  id uuid primary key default gen_random_uuid(),
  device_id text not null,
  token_hash text not null,
  label text not null default 'default',
  created_at timestamptz not null default now(),
  revoked_at timestamptz,
  last_used_at timestamptz,
  unique (device_id, label)
);

create table if not exists public.agent_sessions (
  id uuid primary key default gen_random_uuid(),
  device_id text not null,
  started_at timestamptz not null default now(),
  last_seen_at timestamptz not null default now(),
  remote_mode text not null default 'supabase',
  metadata jsonb not null default '{}'::jsonb
);

create table if not exists public.agent_messages (
  id bigserial primary key,
  device_id text not null,
  level text not null default 'info',
  message text not null,
  source text not null default 'supervisor',
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists idx_agent_messages_device_time
  on public.agent_messages (device_id, created_at desc);

-- ---------------------------------------------------------------------------
-- Auth helper (token hash)
-- ---------------------------------------------------------------------------
create or replace function public._agent_auth_ok(p_device_id text, p_agent_token text)
returns boolean
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
  v_hash text;
begin
  if p_agent_token is null or length(trim(p_agent_token)) < 16 then
    return false;
  end if;
  v_hash := encode(digest(p_agent_token, 'sha256'), 'hex');
  if exists (
    select 1 from public.agent_api_tokens t
    where t.device_id = p_device_id
      and t.token_hash = v_hash
      and t.revoked_at is null
  ) then
    update public.agent_api_tokens
      set last_used_at = now()
      where device_id = p_device_id and token_hash = v_hash and revoked_at is null;
    return true;
  end if;
  return false;
end;
$$;

create or replace function public._agent_resolve_device_uuid(p_device_id text)
returns uuid
language sql
stable
security definer
set search_path = public, pg_temp
as $$
  select d.id
  from public.devices d
  where d.device_id = p_device_id or d.code = p_device_id
  order by case when d.device_id = p_device_id then 0 else 1 end
  limit 1;
$$;

-- ---------------------------------------------------------------------------
-- RPC: agent_heartbeat
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
  v_uuid uuid;
  v_status text;
begin
  if not public._agent_auth_ok(p_device_id, p_agent_token) then
    raise exception 'agent auth failed' using errcode = '42501';
  end if;

  v_status := upper(coalesce(p_status, 'ONLINE'));
  if v_status = 'OFFLINE' then
    v_status := 'DEGRADED';
  end if;

  v_uuid := public._agent_resolve_device_uuid(p_device_id);

  if v_uuid is null then
    insert into public.devices (
      id, code, device_id, name, status,
      agent_version, vision_version, platform_version,
      last_seen_at, current_job_id, modules, updated_at
    ) values (
      gen_random_uuid(),
      p_device_id,
      p_device_id,
      p_device_id,
      v_status,
      coalesce(p_agent_version, ''),
      coalesce(p_vision_version, ''),
      coalesce(p_platform_version, ''),
      coalesce(p_timestamp, now()),
      nullif(p_current_job_id, ''),
      coalesce(p_modules, '[]'::jsonb),
      now()
    )
    returning id into v_uuid;
  else
    update public.devices d set
      device_id = coalesce(nullif(trim(d.device_id), ''), p_device_id),
      code = coalesce(nullif(trim(d.code), ''), p_device_id),
      status = v_status,
      agent_version = coalesce(p_agent_version, d.agent_version),
      vision_version = coalesce(p_vision_version, d.vision_version),
      platform_version = coalesce(p_platform_version, d.platform_version),
      last_seen_at = coalesce(p_timestamp, now()),
      current_job_id = nullif(p_current_job_id, ''),
      modules = coalesce(p_modules, d.modules),
      updated_at = now()
    where d.id = v_uuid;
  end if;

  insert into public.heartbeats (
    device_id, status, agent_version, vision_version, platform_version,
    current_job_id, modules, recorded_at, payload
  ) values (
    p_device_id, v_status, p_agent_version, p_vision_version, p_platform_version,
    nullif(p_current_job_id, ''), coalesce(p_modules, '[]'::jsonb),
    coalesce(p_timestamp, now()),
    jsonb_build_object('source', 'agent_heartbeat')
  );

  insert into public.agent_sessions (device_id, last_seen_at, remote_mode)
  values (p_device_id, coalesce(p_timestamp, now()), 'supabase');

  return jsonb_build_object('ok', true, 'device_id', p_device_id, 'status', v_status);
end;
$$;

-- ---------------------------------------------------------------------------
-- RPC: agent_fetch_pending_commands
-- Returns Agent-shaped rows (command_id, target_device_id TEXT logical).
-- Maps PWA commands.id → command_id; resolves uuid target → logical device_id.
-- ---------------------------------------------------------------------------
create or replace function public.agent_fetch_pending_commands(
  p_device_id text,
  p_agent_token text,
  p_limit int default 10
)
returns table (
  command_id uuid,
  command_type text,
  target_device_id text,
  status text,
  parameters jsonb,
  requested_at timestamptz,
  expires_at timestamptz,
  acknowledged_at timestamptz,
  started_at timestamptz,
  finished_at timestamptz,
  result jsonb,
  error text,
  created_at timestamptz
)
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
  v_uuid uuid;
begin
  if not public._agent_auth_ok(p_device_id, p_agent_token) then
    raise exception 'agent auth failed' using errcode = '42501';
  end if;

  v_uuid := public._agent_resolve_device_uuid(p_device_id);

  return query
  select
    c.id as command_id,
    c.command_type::text,
    p_device_id as target_device_id,
    c.status::text,
    coalesce(c.parameters, '{}'::jsonb) as parameters,
    c.requested_at,
    c.expires_at,
    c.acknowledged_at,
    c.started_at,
    c.finished_at,
    c.result,
    c.error,
    coalesce(c.created_at, c.requested_at) as created_at
  from public.commands c
  where c.status::text = 'PENDING'
    and (c.expires_at is null or c.expires_at > now())
    and (
      (v_uuid is not null and c.target_device_id = v_uuid)
      or c.target_device_id::text = p_device_id
    )
    and c.command_type::text in (
      'GET_STATUS',
      'WAKE_SUPERVISOR',
      'DEACTIVATE_SUPERVISOR'
    )
  order by c.requested_at asc nulls last
  limit greatest(1, least(coalesce(p_limit, 10), 50));
end;
$$;

-- ---------------------------------------------------------------------------
-- RPC: agent_update_command
-- ---------------------------------------------------------------------------
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
  v_uuid uuid;
  v_row public.commands;
begin
  if not public._agent_auth_ok(p_device_id, p_agent_token) then
    raise exception 'agent auth failed' using errcode = '42501';
  end if;

  v_uuid := public._agent_resolve_device_uuid(p_device_id);

  update public.commands c
  set
    status = p_status,
    result = coalesce(p_result, c.result),
    error = coalesce(p_error, c.error),
    acknowledged_at = coalesce(p_acknowledged_at, c.acknowledged_at),
    started_at = coalesce(p_started_at, c.started_at),
    finished_at = coalesce(p_finished_at, c.finished_at),
    updated_at = now()
  where c.id = p_command_id
    and (
      (v_uuid is not null and c.target_device_id = v_uuid)
      or c.target_device_id::text = p_device_id
    )
  returning * into v_row;

  if v_row.id is null then
    raise exception 'command not found' using errcode = 'P0002';
  end if;

  return jsonb_build_object(
    'ok', true,
    'command_id', v_row.id,
    'status', v_row.status
  );
end;
$$;

-- ---------------------------------------------------------------------------
-- RPC: agent_publish_message (optional inbound feed for PWA / observers)
-- ---------------------------------------------------------------------------
create or replace function public.agent_publish_message(
  p_device_id text,
  p_agent_token text,
  p_message text,
  p_level text default 'info',
  p_source text default 'supervisor',
  p_metadata jsonb default '{}'::jsonb
)
returns jsonb
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
  v_id bigint;
begin
  if not public._agent_auth_ok(p_device_id, p_agent_token) then
    raise exception 'agent auth failed' using errcode = '42501';
  end if;
  if p_message is null or length(trim(p_message)) = 0 then
    raise exception 'empty message' using errcode = '22023';
  end if;

  insert into public.agent_messages (device_id, level, message, source, metadata)
  values (
    p_device_id,
    coalesce(nullif(trim(p_level), ''), 'info'),
    left(trim(p_message), 2000),
    coalesce(nullif(trim(p_source), ''), 'supervisor'),
    coalesce(p_metadata, '{}'::jsonb)
  )
  returning id into v_id;

  return jsonb_build_object('ok', true, 'id', v_id);
end;
$$;

-- Helper: enqueue thin command by logical device id (SQL Editor / PWA)
create or replace function public.enqueue_supervisor_command(
  p_device_id text,
  p_command_type text
)
returns uuid
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
  v_uuid uuid;
  v_cmd uuid;
  v_type text := upper(trim(p_command_type));
begin
  if v_type not in ('WAKE_SUPERVISOR', 'DEACTIVATE_SUPERVISOR', 'GET_STATUS') then
    raise exception 'thin channel: command not allowed: %', v_type using errcode = '42501';
  end if;
  v_uuid := public._agent_resolve_device_uuid(p_device_id);
  if v_uuid is null then
    raise exception 'device not found: %', p_device_id using errcode = 'P0002';
  end if;

  insert into public.commands (
    command_type, module_id, target_device_id, parameters,
    requested_at, expires_at, status
  ) values (
    v_type, 'core', v_uuid, '{}'::jsonb,
    now(), now() + interval '5 minutes', 'PENDING'
  )
  returning id into v_cmd;

  return v_cmd;
end;
$$;

-- ---------------------------------------------------------------------------
-- RLS (additive; do not revoke existing PWA policies aggressively)
-- ---------------------------------------------------------------------------
alter table public.heartbeats enable row level security;
alter table public.agent_api_tokens enable row level security;
alter table public.agent_sessions enable row level security;
alter table public.agent_messages enable row level security;

drop policy if exists heartbeats_select_auth on public.heartbeats;
create policy heartbeats_select_auth on public.heartbeats
  for select to authenticated using (true);

drop policy if exists agent_messages_select_auth on public.agent_messages;
create policy agent_messages_select_auth on public.agent_messages
  for select to authenticated using (true);

drop policy if exists agent_tokens_admin_all on public.agent_api_tokens;
create policy agent_tokens_admin_all on public.agent_api_tokens
  for all to authenticated
  using (true)
  with check (true);
-- NOTE: tighten to ADMIN-only once PWA role helpers exist; tokens never readable by anon.

drop policy if exists agent_sessions_select_auth on public.agent_sessions;
create policy agent_sessions_select_auth on public.agent_sessions
  for select to authenticated using (true);

revoke all on table public.heartbeats from anon, public;
revoke all on table public.agent_api_tokens from anon, public;
revoke all on table public.agent_sessions from anon, public;
revoke all on table public.agent_messages from anon, public;

grant select on table public.heartbeats to authenticated;
grant select on table public.agent_messages to authenticated;
grant select on table public.agent_sessions to authenticated;
grant select, insert, update, delete on table public.agent_api_tokens to authenticated;

-- RPC grants: Agent uses anon key + token arg
grant execute on function public.agent_heartbeat(
  text, text, text, text, text, text, text, jsonb, timestamptz
) to anon, authenticated;
grant execute on function public.agent_fetch_pending_commands(text, text, int)
  to anon, authenticated;
grant execute on function public.agent_update_command(
  text, text, uuid, text, jsonb, text, timestamptz, timestamptz, timestamptz
) to anon, authenticated;
grant execute on function public.agent_publish_message(
  text, text, text, text, text, jsonb
) to anon, authenticated;
grant execute on function public.enqueue_supervisor_command(text, text)
  to authenticated;

comment on function public.agent_heartbeat is
  'Thin channel: Agent presence. Auth = SHA-256(VISION_AGENT_TOKEN) vs agent_api_tokens.';
comment on function public.agent_fetch_pending_commands is
  'Thin channel: GET_STATUS | WAKE_SUPERVISOR | DEACTIVATE_SUPERVISOR only.';
comment on table public.agent_messages is
  'Thin inbound message feed from Agent supervisor (not a job store).';
