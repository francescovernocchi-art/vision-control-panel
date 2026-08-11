ALTER TABLE public.agent_messages
  ADD COLUMN IF NOT EXISTS direction text NOT NULL DEFAULT 'IN',
  ADD COLUMN IF NOT EXISTS author_id uuid REFERENCES auth.users(id) ON DELETE SET NULL,
  ADD COLUMN IF NOT EXISTS delivered_at timestamptz;

DO $$ BEGIN
  ALTER TABLE public.agent_messages ADD CONSTRAINT agent_messages_direction_chk CHECK (direction IN ('IN','OUT'));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

CREATE INDEX IF NOT EXISTS agent_messages_device_created_idx ON public.agent_messages(device_id, created_at DESC);

GRANT SELECT, INSERT, UPDATE ON public.agent_messages TO authenticated;
GRANT ALL ON public.agent_messages TO service_role;

DROP POLICY IF EXISTS "agent messages send by operators" ON public.agent_messages;
CREATE POLICY "agent messages send by operators"
ON public.agent_messages FOR INSERT TO authenticated
WITH CHECK (direction = 'OUT' AND author_id = auth.uid() AND public.can_operate(auth.uid()));

CREATE OR REPLACE FUNCTION public.agent_fetch_outbound_messages(p_device_id text, p_token text, p_limit integer DEFAULT 50)
RETURNS SETOF jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path TO 'public','pg_temp'
AS $function$
DECLARE r record;
BEGIN
  IF NOT public.agent_verify_token(p_device_id, p_token) THEN
    RAISE EXCEPTION 'invalid agent token';
  END IF;
  FOR r IN
    SELECT * FROM public.agent_messages
    WHERE device_id = p_device_id AND direction = 'OUT' AND delivered_at IS NULL
    ORDER BY created_at ASC
    LIMIT GREATEST(COALESCE(p_limit,50),1)
  LOOP
    UPDATE public.agent_messages SET delivered_at = now() WHERE id = r.id;
    RETURN NEXT jsonb_build_object(
      'message_id', r.id, 'device_id', r.device_id, 'body', r.body,
      'title', r.title, 'payload', r.payload, 'created_at', r.created_at);
  END LOOP;
END; $function$;