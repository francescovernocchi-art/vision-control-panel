CREATE OR REPLACE FUNCTION public.enqueue_supervisor_command(p_device_id text, p_command_type text)
 RETURNS uuid
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public', 'pg_temp'
AS $function$
DECLARE v_id uuid; v_uuid uuid; v_type text := upper(p_command_type);
BEGIN
  IF v_type NOT IN ('WAKE_SUPERVISOR','DEACTIVATE_SUPERVISOR','GET_STATUS') THEN
    RAISE EXCEPTION 'command type % not allowed on the thin channel', p_command_type;
  END IF;
  SELECT id INTO v_uuid FROM public.devices WHERE device_id = p_device_id OR code = p_device_id LIMIT 1;
  IF v_uuid IS NULL THEN RAISE EXCEPTION 'unknown device %', p_device_id; END IF;

  INSERT INTO public.commands(command_type, target_device_id, target_device_code, requested_by, status, expires_at)
  VALUES (v_type, v_uuid, p_device_id, auth.uid(), 'PENDING', NULL)
  RETURNING id INTO v_id;
  RETURN v_id;
END; $function$;