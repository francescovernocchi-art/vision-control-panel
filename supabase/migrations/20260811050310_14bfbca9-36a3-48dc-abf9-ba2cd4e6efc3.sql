CREATE OR REPLACE FUNCTION public.agent_verify_token(p_device_id text, p_token text)
RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE v_ok integer;
BEGIN
  UPDATE public.agent_api_tokens
     SET last_used_at = now()
   WHERE device_id = p_device_id
     AND revoked_at IS NULL
     AND token_hash = encode(sha256(convert_to(coalesce(p_token,''), 'utf8')), 'hex');
  GET DIAGNOSTICS v_ok = ROW_COUNT;
  RETURN COALESCE(v_ok, 0) > 0;
END; $$;
REVOKE ALL ON FUNCTION public.agent_verify_token(text, text) FROM public, anon, authenticated;