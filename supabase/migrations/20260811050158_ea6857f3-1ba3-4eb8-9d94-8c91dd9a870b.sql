-- =========================================================
-- VISION thin channel: additive alignment (PWA-compatible)
-- =========================================================

-- A) devices: additive columns only
ALTER TABLE public.devices ADD COLUMN IF NOT EXISTS device_id text;
ALTER TABLE public.devices ADD COLUMN IF NOT EXISTS vision_version text;
ALTER TABLE public.devices ADD COLUMN IF NOT EXISTS platform_version text;
ALTER TABLE public.devices ADD COLUMN IF NOT EXISTS modules jsonb NOT NULL DEFAULT '[]'::jsonb;

UPDATE public.devices SET device_id = code WHERE device_id IS NULL AND code IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS devices_device_id_key ON public.devices(device_id);

INSERT INTO public.devices (code, device_id, name, location, status)
SELECT 'VIS-TARANTO-01', 'VIS-TARANTO-01', 'VIS Taranto 01', 'Taranto', 'OFFLINE'
WHERE NOT EXISTS (SELECT 1 FROM public.devices WHERE device_id = 'VIS-TARANTO-01' OR code = 'VIS-TARANTO-01');

UPDATE public.devices SET device_id = 'VIS-TARANTO-01'
WHERE code = 'VIS-TARANTO-01' AND device_id IS NULL;

-- B) new tables
CREATE TABLE IF NOT EXISTS public.heartbeats (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  device_id text NOT NULL,
  status text NOT NULL DEFAULT 'ONLINE',
  agent_version text,
  vision_version text,
  platform_version text,
  modules jsonb NOT NULL DEFAULT '[]'::jsonb,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS heartbeats_device_created_idx ON public.heartbeats(device_id, created_at DESC);
GRANT SELECT ON public.heartbeats TO authenticated;
GRANT ALL ON public.heartbeats TO service_role;
ALTER TABLE public.heartbeats ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "heartbeats read" ON public.heartbeats;
CREATE POLICY "heartbeats read" ON public.heartbeats FOR SELECT TO authenticated USING (true);

CREATE TABLE IF NOT EXISTS public.agent_api_tokens (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  device_id text NOT NULL,
  token_hash text NOT NULL,
  label text NOT NULL DEFAULT 'default',
  created_at timestamptz NOT NULL DEFAULT now(),
  last_used_at timestamptz,
  revoked_at timestamptz,
  UNIQUE (device_id, label)
);
CREATE INDEX IF NOT EXISTS agent_api_tokens_hash_idx ON public.agent_api_tokens(token_hash);
GRANT SELECT, INSERT, UPDATE, DELETE ON public.agent_api_tokens TO authenticated;
GRANT ALL ON public.agent_api_tokens TO service_role;
ALTER TABLE public.agent_api_tokens ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "agent tokens admin" ON public.agent_api_tokens;
CREATE POLICY "agent tokens admin" ON public.agent_api_tokens FOR ALL TO authenticated
  USING (public.has_role(auth.uid(), 'ADMIN'::app_role))
  WITH CHECK (public.has_role(auth.uid(), 'ADMIN'::app_role));

CREATE TABLE IF NOT EXISTS public.agent_sessions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  device_id text NOT NULL,
  started_at timestamptz NOT NULL DEFAULT now(),
  last_seen_at timestamptz NOT NULL DEFAULT now(),
  ended_at timestamptz,
  agent_version text,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS agent_sessions_device_idx ON public.agent_sessions(device_id, started_at DESC);
GRANT SELECT ON public.agent_sessions TO authenticated;
GRANT ALL ON public.agent_sessions TO service_role;
ALTER TABLE public.agent_sessions ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "agent sessions read" ON public.agent_sessions;
CREATE POLICY "agent sessions read" ON public.agent_sessions FOR SELECT TO authenticated USING (true);

CREATE TABLE IF NOT EXISTS public.agent_messages (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  device_id text NOT NULL,
  message_type text NOT NULL DEFAULT 'SUPERVISOR',
  level text NOT NULL DEFAULT 'INFO',
  title text,
  body text,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  command_id uuid,
  created_at timestamptz NOT NULL DEFAULT now(),
  read_at timestamptz
);
CREATE INDEX IF NOT EXISTS agent_messages_device_created_idx ON public.agent_messages(device_id, created_at DESC);
GRANT SELECT, UPDATE ON public.agent_messages TO authenticated;
GRANT ALL ON public.agent_messages TO service_role;
ALTER TABLE public.agent_messages ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "agent messages read" ON public.agent_messages;
CREATE POLICY "agent messages read" ON public.agent_messages FOR SELECT TO authenticated USING (true);
DROP POLICY IF EXISTS "agent messages mark read" ON public.agent_messages;
CREATE POLICY "agent messages mark read" ON public.agent_messages FOR UPDATE TO authenticated USING (true) WITH CHECK (true);

-- commands: lifecycle columns + thin command types
ALTER TABLE public.commands ADD COLUMN IF NOT EXISTS expires_at timestamptz;
ALTER TABLE public.commands ADD COLUMN IF NOT EXISTS acknowledged_at timestamptz;
ALTER TABLE public.commands ADD COLUMN IF NOT EXISTS started_at timestamptz;
ALTER TABLE public.commands ADD COLUMN IF NOT EXISTS finished_at timestamptz;
ALTER TABLE public.commands ADD COLUMN IF NOT EXISTS progress integer NOT NULL DEFAULT 0;
ALTER TABLE public.commands ADD COLUMN IF NOT EXISTS target_device_code text;
ALTER TABLE public.commands ALTER COLUMN requested_by DROP NOT NULL;

ALTER TABLE public.commands DROP CONSTRAINT IF EXISTS commands_command_type_check;
ALTER TABLE public.commands ADD CONSTRAINT commands_command_type_check CHECK (command_type = ANY (ARRAY[
  'GET_STATUS','WAKE_SUPERVISOR','DEACTIVATE_SUPERVISOR',
  'CHECK_ENISPACE_MAIL','RETRY_JOB','PAUSE_MODULE','RESUME_MODULE',
  'PREPARE_COIN_TRANSPORT','APPROVE_JOB','REJECT_JOB']));

UPDATE public.commands c SET target_device_code = d.device_id
FROM public.devices d WHERE c.target_device_id = d.id AND c.target_device_code IS NULL;

CREATE INDEX IF NOT EXISTS commands_device_status_idx ON public.commands(target_device_code, status);

-- C) RPCs
CREATE OR REPLACE FUNCTION public.agent_verify_token(p_device_id text, p_token text)
RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE v_ok boolean;
BEGIN
  UPDATE public.agent_api_tokens
     SET last_used_at = now()
   WHERE device_id = p_device_id
     AND revoked_at IS NULL
     AND token_hash = encode(digest(coalesce(p_token,''), 'sha256'), 'hex');
  GET DIAGNOSTICS v_ok = ROW_COUNT;
  RETURN COALESCE(v_ok, false);
END; $$;
REVOKE ALL ON FUNCTION public.agent_verify_token(text, text) FROM public, anon, authenticated;

CREATE OR REPLACE FUNCTION public.agent_heartbeat(
  p_device_id text,
  p_token text,
  p_status text DEFAULT 'ONLINE',
  p_agent_version text DEFAULT NULL,
  p_vision_version text DEFAULT NULL,
  p_platform_version text DEFAULT NULL,
  p_modules jsonb DEFAULT '[]'::jsonb,
  p_payload jsonb DEFAULT '{}'::jsonb
) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE v_status text;
BEGIN
  IF NOT public.agent_verify_token(p_device_id, p_token) THEN
    RAISE EXCEPTION 'invalid agent token';
  END IF;
  -- devices.status is plain text in the PWA schema; keep the PWA vocabulary.
  v_status := CASE WHEN upper(coalesce(p_status,'ONLINE')) IN ('ONLINE','OFFLINE','BUSY','ERROR')
                   THEN upper(p_status) ELSE 'ONLINE' END;

  UPDATE public.devices SET
    status = v_status,
    last_seen_at = now(),
    agent_version = COALESCE(p_agent_version, agent_version),
    vision_version = COALESCE(p_vision_version, vision_version),
    platform_version = COALESCE(p_platform_version, platform_version),
    modules = COALESCE(p_modules, modules),
    updated_at = now()
  WHERE device_id = p_device_id;

  INSERT INTO public.heartbeats(device_id, status, agent_version, vision_version, platform_version, modules, payload)
  VALUES (p_device_id, v_status, p_agent_version, p_vision_version, p_platform_version, COALESCE(p_modules,'[]'::jsonb), COALESCE(p_payload,'{}'::jsonb));

  INSERT INTO public.agent_sessions(device_id, agent_version)
  SELECT p_device_id, p_agent_version
  WHERE NOT EXISTS (
    SELECT 1 FROM public.agent_sessions
    WHERE device_id = p_device_id AND ended_at IS NULL AND last_seen_at > now() - interval '10 minutes'
  );
  UPDATE public.agent_sessions SET last_seen_at = now()
  WHERE device_id = p_device_id AND ended_at IS NULL;

  RETURN jsonb_build_object('ok', true, 'device_id', p_device_id, 'status', v_status, 'server_time', now());
END; $$;
GRANT EXECUTE ON FUNCTION public.agent_heartbeat(text,text,text,text,text,text,jsonb,jsonb) TO anon, authenticated, service_role;

CREATE OR REPLACE FUNCTION public.agent_fetch_pending_commands(
  p_device_id text, p_token text, p_limit integer DEFAULT 20
) RETURNS SETOF jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
BEGIN
  IF NOT public.agent_verify_token(p_device_id, p_token) THEN
    RAISE EXCEPTION 'invalid agent token';
  END IF;
  RETURN QUERY
  SELECT jsonb_build_object(
    'command_id', c.id, 'id', c.id, 'command_type', c.command_type,
    'device_id', p_device_id, 'parameters', c.parameters,
    'requested_at', c.requested_at, 'expires_at', c.expires_at, 'status', c.status)
  FROM public.commands c
  LEFT JOIN public.devices d ON d.id = c.target_device_id
  WHERE (c.target_device_code = p_device_id OR d.device_id = p_device_id)
    AND c.status = 'PENDING'
    AND (c.expires_at IS NULL OR c.expires_at > now())
    AND c.command_type IN ('WAKE_SUPERVISOR','DEACTIVATE_SUPERVISOR','GET_STATUS')
  ORDER BY c.requested_at ASC
  LIMIT GREATEST(COALESCE(p_limit,20), 1);
END; $$;
GRANT EXECUTE ON FUNCTION public.agent_fetch_pending_commands(text,text,integer) TO anon, authenticated, service_role;

CREATE OR REPLACE FUNCTION public.agent_update_command(
  p_device_id text, p_token text, p_command_id uuid, p_status text,
  p_result jsonb DEFAULT NULL, p_error text DEFAULT NULL, p_progress integer DEFAULT NULL
) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE v_status text := upper(p_status);
BEGIN
  IF NOT public.agent_verify_token(p_device_id, p_token) THEN
    RAISE EXCEPTION 'invalid agent token';
  END IF;
  IF v_status NOT IN ('ACKNOWLEDGED','EXECUTING','COMPLETED','FAILED','REJECTED') THEN
    RAISE EXCEPTION 'invalid status %', p_status;
  END IF;

  UPDATE public.commands c SET
    status = v_status,
    progress = COALESCE(p_progress, c.progress),
    result = COALESCE(p_result, c.result),
    error = COALESCE(p_error, c.error),
    acknowledged_at = CASE WHEN v_status = 'ACKNOWLEDGED' THEN now() ELSE c.acknowledged_at END,
    started_at = CASE WHEN v_status = 'EXECUTING' THEN COALESCE(c.started_at, now()) ELSE c.started_at END,
    finished_at = CASE WHEN v_status IN ('COMPLETED','FAILED','REJECTED') THEN now() ELSE c.finished_at END,
    executed_at = CASE WHEN v_status IN ('COMPLETED','FAILED','REJECTED') THEN now() ELSE c.executed_at END
  WHERE c.id = p_command_id
    AND (c.target_device_code = p_device_id
         OR EXISTS (SELECT 1 FROM public.devices d WHERE d.id = c.target_device_id AND d.device_id = p_device_id));

  IF NOT FOUND THEN
    RAISE EXCEPTION 'command not found for device';
  END IF;
  RETURN jsonb_build_object('ok', true, 'command_id', p_command_id, 'status', v_status);
END; $$;
GRANT EXECUTE ON FUNCTION public.agent_update_command(text,text,uuid,text,jsonb,text,integer) TO anon, authenticated, service_role;

CREATE OR REPLACE FUNCTION public.agent_publish_message(
  p_device_id text, p_token text, p_body text,
  p_title text DEFAULT NULL, p_level text DEFAULT 'INFO',
  p_message_type text DEFAULT 'SUPERVISOR',
  p_payload jsonb DEFAULT '{}'::jsonb, p_command_id uuid DEFAULT NULL
) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE v_id uuid;
BEGIN
  IF NOT public.agent_verify_token(p_device_id, p_token) THEN
    RAISE EXCEPTION 'invalid agent token';
  END IF;
  INSERT INTO public.agent_messages(device_id, message_type, level, title, body, payload, command_id)
  VALUES (p_device_id, COALESCE(p_message_type,'SUPERVISOR'), COALESCE(upper(p_level),'INFO'), p_title, p_body,
          COALESCE(p_payload,'{}'::jsonb), p_command_id)
  RETURNING id INTO v_id;
  RETURN jsonb_build_object('ok', true, 'message_id', v_id);
END; $$;
GRANT EXECUTE ON FUNCTION public.agent_publish_message(text,text,text,text,text,text,jsonb,uuid) TO anon, authenticated, service_role;

CREATE OR REPLACE FUNCTION public.enqueue_supervisor_command(p_device_id text, p_command_type text)
RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE v_id uuid; v_uuid uuid; v_type text := upper(p_command_type);
BEGIN
  IF v_type NOT IN ('WAKE_SUPERVISOR','DEACTIVATE_SUPERVISOR','GET_STATUS') THEN
    RAISE EXCEPTION 'command type % not allowed on the thin channel', p_command_type;
  END IF;
  SELECT id INTO v_uuid FROM public.devices WHERE device_id = p_device_id OR code = p_device_id LIMIT 1;
  IF v_uuid IS NULL THEN RAISE EXCEPTION 'unknown device %', p_device_id; END IF;

  INSERT INTO public.commands(command_type, target_device_id, target_device_code, requested_by, status, expires_at)
  VALUES (v_type, v_uuid, p_device_id, auth.uid(), 'PENDING', now() + interval '5 minutes')
  RETURNING id INTO v_id;
  RETURN v_id;
END; $$;
GRANT EXECUTE ON FUNCTION public.enqueue_supervisor_command(text,text) TO authenticated, service_role;

-- PWA compatibility: GET_STATUS helper used by the mobile app
CREATE OR REPLACE FUNCTION public.create_get_status_command(p_device_id text)
RETURNS uuid LANGUAGE sql SECURITY DEFINER SET search_path = public, pg_temp AS $$
  SELECT public.enqueue_supervisor_command(p_device_id, 'GET_STATUS');
$$;
GRANT EXECUTE ON FUNCTION public.create_get_status_command(text) TO authenticated, service_role;