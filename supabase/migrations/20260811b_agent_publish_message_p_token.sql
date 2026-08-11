-- Align agent_publish_message with live Lovable p_token arg name.
-- Safe to re-run. Does not touch devices / commands schema.

create or replace function public.agent_publish_message(
  p_device_id text,
  p_token text,
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
  if not public._agent_auth_ok(p_device_id, p_token) then
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

grant execute on function public.agent_publish_message(
  text, text, text, text, text, jsonb
) to anon, authenticated;

comment on function public.agent_publish_message is
  'Thin inbound feed. Auth = SHA-256(VISION_AGENT_TOKEN) via p_token.';
