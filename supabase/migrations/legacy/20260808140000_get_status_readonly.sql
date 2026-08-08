-- VIS•ION Mobile — bridge GET_STATUS ONLY sul schema Lovable esistente
-- Contratto ufficiale: vis-ion/docs/VISION_REMOTE_PWA_CONTRACT.md
-- RPC esatta: create_get_status_command(p_device_id text) → commands row
-- p_device_id = device code testuale (es. VIS-TARANTO-01), non UUID.
--
-- Nota schema: la PWA Lovable usa devices.id (uuid) + devices.code;
-- user_devices è già usata per push endpoints → autorizzazione device in device_access.
-- Agent Python può restare sullo schema text-PK; questa migration adatta SOLO la PWA.

-- Colonne lifecycle comandi (Agent)
ALTER TABLE public.commands
  ADD COLUMN IF NOT EXISTS expires_at timestamptz,
  ADD COLUMN IF NOT EXISTS acknowledged_at timestamptz,
  ADD COLUMN IF NOT EXISTS started_at timestamptz,
  ADD COLUMN IF NOT EXISTS finished_at timestamptz;

ALTER TABLE public.devices
  ADD COLUMN IF NOT EXISTS platform_version text,
  ADD COLUMN IF NOT EXISTS vision_version text;

UPDATE public.devices
SET heartbeat_threshold_seconds = 60
WHERE code = 'VIS-TARANTO-01'
  AND COALESCE(heartbeat_threshold_seconds, 120) = 120;

-- Heartbeats append-only (Agent / read PWA)
CREATE TABLE IF NOT EXISTS public.heartbeats (
  id bigserial PRIMARY KEY,
  device_id uuid NOT NULL REFERENCES public.devices(id) ON DELETE CASCADE,
  status text NOT NULL,
  agent_version text,
  vision_version text,
  platform_version text,
  current_job_id text,
  modules jsonb NOT NULL DEFAULT '[]'::jsonb,
  recorded_at timestamptz NOT NULL DEFAULT now(),
  payload jsonb NOT NULL DEFAULT '{}'::jsonb
);
ALTER TABLE public.heartbeats ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "heartbeats read authenticated" ON public.heartbeats;
CREATE POLICY "heartbeats read authenticated"
  ON public.heartbeats FOR SELECT TO authenticated USING (true);
GRANT SELECT ON public.heartbeats TO authenticated;
GRANT ALL ON public.heartbeats TO service_role;

-- Token Agent (hash only) — PWA NON legge se non ADMIN
CREATE TABLE IF NOT EXISTS public.agent_api_tokens (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  device_id uuid NOT NULL REFERENCES public.devices(id) ON DELETE CASCADE,
  token_hash text NOT NULL,
  label text NOT NULL DEFAULT 'default',
  created_at timestamptz NOT NULL DEFAULT now(),
  revoked_at timestamptz,
  last_used_at timestamptz,
  UNIQUE (device_id, label)
);
ALTER TABLE public.agent_api_tokens ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "agent_tokens admin only" ON public.agent_api_tokens;
CREATE POLICY "agent_tokens admin only"
  ON public.agent_api_tokens FOR ALL TO authenticated
  USING (public.has_role(auth.uid(), 'ADMIN'))
  WITH CHECK (public.has_role(auth.uid(), 'ADMIN'));
GRANT ALL ON public.agent_api_tokens TO service_role;

-- Autorizzazione utente ↔ device (contratto: user_devices; qui device_access
-- perché user_devices Lovable = push endpoints)
CREATE TABLE IF NOT EXISTS public.device_access (
  user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  device_id uuid NOT NULL REFERENCES public.devices(id) ON DELETE CASCADE,
  can_command boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (user_id, device_id)
);
ALTER TABLE public.device_access ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "device_access own or admin" ON public.device_access;
CREATE POLICY "device_access own or admin"
  ON public.device_access FOR SELECT TO authenticated
  USING (user_id = auth.uid() OR public.has_role(auth.uid(), 'ADMIN'));
DROP POLICY IF EXISTS "device_access admin write" ON public.device_access;
CREATE POLICY "device_access admin write"
  ON public.device_access FOR ALL TO authenticated
  USING (public.has_role(auth.uid(), 'ADMIN'))
  WITH CHECK (public.has_role(auth.uid(), 'ADMIN'));
GRANT SELECT ON public.device_access TO authenticated;
GRANT ALL ON public.device_access TO service_role;

CREATE OR REPLACE VIEW public.devices_with_derived_status AS
SELECT
  d.*,
  CASE
    WHEN d.status = 'DISABLED' THEN 'DISABLED'
    WHEN d.last_seen_at IS NULL THEN 'OFFLINE'
    WHEN now() - d.last_seen_at >
      make_interval(secs => COALESCE(d.heartbeat_threshold_seconds, 60))
      THEN 'OFFLINE'
    ELSE d.status
  END AS derived_status
FROM public.devices d;

CREATE OR REPLACE FUNCTION public.enforce_status_only_commands()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  IF TG_OP = 'INSERT' AND NEW.command_type <> 'GET_STATUS' THEN
    RAISE EXCEPTION 'REMOTE_OPERATION_NOT_ENABLED: solo GET_STATUS consentito in questa fase'
      USING ERRCODE = '42501';
  END IF;
  IF TG_OP = 'INSERT' AND NEW.expires_at IS NULL THEN
    NEW.expires_at := now() + interval '2 minutes';
  END IF;
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_commands_status_only ON public.commands;
CREATE TRIGGER trg_commands_status_only
BEFORE INSERT ON public.commands
FOR EACH ROW EXECUTE FUNCTION public.enforce_status_only_commands();

-- Contratto: create_get_status_command(p_device_id text)
CREATE OR REPLACE FUNCTION public.create_get_status_command(p_device_id text)
RETURNS public.commands
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
  v_uid uuid := auth.uid();
  v_device public.devices;
  v_cmd public.commands;
  v_core_module uuid;
BEGIN
  IF v_uid IS NULL THEN
    RAISE EXCEPTION 'not authenticated' USING ERRCODE = '42501';
  END IF;
  IF public.has_role(v_uid, 'DIREZIONE')
     AND NOT public.has_role(v_uid, 'ADMIN')
     AND NOT public.has_role(v_uid, 'OPERATORE') THEN
    RAISE EXCEPTION 'DIREZIONE cannot create commands' USING ERRCODE = '42501';
  END IF;
  IF NOT public.can_operate(v_uid) THEN
    RAISE EXCEPTION 'role cannot create commands' USING ERRCODE = '42501';
  END IF;

  SELECT * INTO v_device FROM public.devices WHERE code = p_device_id LIMIT 1;
  IF v_device.id IS NULL THEN
    RAISE EXCEPTION 'device not found: %', p_device_id USING ERRCODE = 'P0002';
  END IF;

  -- Se esistono assegnazioni, richiedi membership (ADMIN bypass)
  IF EXISTS (SELECT 1 FROM public.device_access LIMIT 1)
     AND NOT public.has_role(v_uid, 'ADMIN') THEN
    IF NOT EXISTS (
      SELECT 1 FROM public.device_access da
      WHERE da.user_id = v_uid AND da.device_id = v_device.id AND da.can_command
    ) THEN
      RAISE EXCEPTION 'device not authorized' USING ERRCODE = '42501';
    END IF;
  END IF;

  SELECT id INTO v_core_module FROM public.modules WHERE key = 'enispace' LIMIT 1;

  INSERT INTO public.commands (
    command_type, module_id, target_device_id, requested_by, status, parameters, expires_at
  ) VALUES (
    'GET_STATUS',
    v_core_module,
    v_device.id,
    v_uid,
    'PENDING',
    jsonb_build_object('api_version', 'v1', 'contract_version', '1.0.0'),
    now() + interval '2 minutes'
  )
  RETURNING * INTO v_cmd;

  INSERT INTO public.audit_logs (user_id, action, device_id, outcome, metadata)
  VALUES (
    v_uid,
    'CREATE_GET_STATUS',
    v_device.id,
    'OK',
    jsonb_build_object(
      'command_id', v_cmd.id,
      'device_id', p_device_id,
      'api_version', 'v1',
      'contract_version', '1.0.0'
    )
  );

  RETURN v_cmd;
END;
$$;

-- Rimuovi overload legacy se presente
DROP FUNCTION IF EXISTS public.create_get_status_command(text, text);

GRANT EXECUTE ON FUNCTION public.create_get_status_command(text) TO authenticated;

COMMENT ON FUNCTION public.create_get_status_command(text) IS
  'Contratto VISION_REMOTE_PWA: p_device_id = VIS-TARANTO-01 (code). Solo GET_STATUS.';
