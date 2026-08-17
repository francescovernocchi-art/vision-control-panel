-- Helper: utente con un ruolo VISION assegnato
CREATE OR REPLACE FUNCTION public.is_vision_user(_user_id uuid)
RETURNS boolean
LANGUAGE sql
STABLE SECURITY DEFINER
SET search_path = public
AS $$
  SELECT _user_id IS NOT NULL AND EXISTS (SELECT 1 FROM public.user_roles WHERE user_id = _user_id)
$$;

-- profiles: solo il proprio profilo o admin
DROP POLICY IF EXISTS "profiles readable by authenticated" ON public.profiles;
CREATE POLICY "profiles read own or admin" ON public.profiles
FOR SELECT TO authenticated
USING (id = auth.uid() OR public.has_role(auth.uid(), 'ADMIN'));

-- user_roles: solo i propri ruoli o admin
DROP POLICY IF EXISTS "roles readable by authenticated" ON public.user_roles;
CREATE POLICY "user_roles read own or admin" ON public.user_roles
FOR SELECT TO authenticated
USING (user_id = auth.uid() OR public.has_role(auth.uid(), 'ADMIN'));

-- Dati operativi: lettura riservata agli utenti con ruolo
DROP POLICY IF EXISTS "devices read" ON public.devices;
CREATE POLICY "devices read" ON public.devices
FOR SELECT TO authenticated USING (public.is_vision_user(auth.uid()));

DROP POLICY IF EXISTS "modules read" ON public.modules;
CREATE POLICY "modules read" ON public.modules
FOR SELECT TO authenticated USING (public.is_vision_user(auth.uid()));

DROP POLICY IF EXISTS "device_modules read" ON public.device_modules;
CREATE POLICY "device_modules read" ON public.device_modules
FOR SELECT TO authenticated USING (public.is_vision_user(auth.uid()));

DROP POLICY IF EXISTS "vision_jobs read" ON public.vision_jobs;
CREATE POLICY "vision_jobs read" ON public.vision_jobs
FOR SELECT TO authenticated USING (public.is_vision_user(auth.uid()));

DROP POLICY IF EXISTS "job_events read" ON public.job_events;
CREATE POLICY "job_events read" ON public.job_events
FOR SELECT TO authenticated USING (public.is_vision_user(auth.uid()));

DROP POLICY IF EXISTS "commands read" ON public.commands;
CREATE POLICY "commands read" ON public.commands
FOR SELECT TO authenticated USING (public.is_vision_user(auth.uid()));

DROP POLICY IF EXISTS "approvals read" ON public.approvals;
CREATE POLICY "approvals read" ON public.approvals
FOR SELECT TO authenticated USING (public.is_vision_user(auth.uid()));

DROP POLICY IF EXISTS "heartbeats read" ON public.heartbeats;
CREATE POLICY "heartbeats read" ON public.heartbeats
FOR SELECT TO authenticated USING (public.is_vision_user(auth.uid()));

DROP POLICY IF EXISTS "agent sessions read" ON public.agent_sessions;
CREATE POLICY "agent sessions read" ON public.agent_sessions
FOR SELECT TO authenticated USING (public.is_vision_user(auth.uid()));

DROP POLICY IF EXISTS "agent messages read" ON public.agent_messages;
CREATE POLICY "agent messages read" ON public.agent_messages
FOR SELECT TO authenticated USING (public.is_vision_user(auth.uid()));

-- app_bootstrap: leggibile finché non c'è un admin (schermata /setup) oppure da utenti con ruolo
DROP POLICY IF EXISTS "bootstrap read" ON public.app_bootstrap;
CREATE POLICY "bootstrap read" ON public.app_bootstrap
FOR SELECT TO authenticated
USING ((NOT public.admin_exists()) OR public.is_vision_user(auth.uid()));

-- agent_messages: update solo operatori e solo sul campo read_at
DROP POLICY IF EXISTS "agent messages mark read" ON public.agent_messages;
CREATE POLICY "agent messages mark read" ON public.agent_messages
FOR UPDATE TO authenticated
USING (public.can_operate(auth.uid()))
WITH CHECK (public.can_operate(auth.uid()));

CREATE OR REPLACE FUNCTION public.agent_messages_only_read_at()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = public
AS $$
BEGIN
  IF NEW.id IS DISTINCT FROM OLD.id
     OR NEW.device_id IS DISTINCT FROM OLD.device_id
     OR NEW.message_type IS DISTINCT FROM OLD.message_type
     OR NEW.level IS DISTINCT FROM OLD.level
     OR NEW.title IS DISTINCT FROM OLD.title
     OR NEW.body IS DISTINCT FROM OLD.body
     OR NEW.payload IS DISTINCT FROM OLD.payload
     OR NEW.command_id IS DISTINCT FROM OLD.command_id
     OR NEW.created_at IS DISTINCT FROM OLD.created_at
     OR NEW.direction IS DISTINCT FROM OLD.direction
     OR NEW.author_id IS DISTINCT FROM OLD.author_id
     OR NEW.delivered_at IS DISTINCT FROM OLD.delivered_at
  THEN
    RAISE EXCEPTION 'only read_at can be updated on agent_messages';
  END IF;
  RETURN NEW;
END; $$;

DROP TRIGGER IF EXISTS agent_messages_only_read_at ON public.agent_messages;
CREATE TRIGGER agent_messages_only_read_at
BEFORE UPDATE ON public.agent_messages
FOR EACH ROW WHEN (current_setting('role', true) <> 'postgres')
EXECUTE FUNCTION public.agent_messages_only_read_at();

-- Funzioni: rimuovi l'accesso pubblico non necessario
REVOKE ALL ON FUNCTION public.handle_new_user() FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.apply_bootstrap_admin() FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.set_updated_at() FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.agent_verify_token(text, text) FROM PUBLIC, anon, authenticated;

REVOKE ALL ON FUNCTION public.has_role(uuid, app_role) FROM PUBLIC, anon;
REVOKE ALL ON FUNCTION public.can_operate(uuid) FROM PUBLIC, anon;
REVOKE ALL ON FUNCTION public.is_vision_user(uuid) FROM PUBLIC, anon;
REVOKE ALL ON FUNCTION public.admin_exists() FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.has_role(uuid, app_role) TO authenticated;
GRANT EXECUTE ON FUNCTION public.can_operate(uuid) TO authenticated;
GRANT EXECUTE ON FUNCTION public.is_vision_user(uuid) TO authenticated;
GRANT EXECUTE ON FUNCTION public.admin_exists() TO authenticated;

REVOKE ALL ON FUNCTION public.enqueue_supervisor_command(text, text) FROM PUBLIC, anon;
REVOKE ALL ON FUNCTION public.create_get_status_command(text) FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.enqueue_supervisor_command(text, text) TO authenticated;
GRANT EXECUTE ON FUNCTION public.create_get_status_command(text) TO authenticated;

-- Funzioni Agent: protette da token, richiamabili solo dal canale Agent (chiave pubblica)
REVOKE ALL ON FUNCTION public.agent_heartbeat(text, text, text, text, text, text, jsonb, jsonb) FROM PUBLIC, authenticated;
REVOKE ALL ON FUNCTION public.agent_fetch_pending_commands(text, text, integer) FROM PUBLIC, authenticated;
REVOKE ALL ON FUNCTION public.agent_fetch_outbound_messages(text, text, integer) FROM PUBLIC, authenticated;
REVOKE ALL ON FUNCTION public.agent_update_command(text, text, uuid, text, jsonb, text, integer) FROM PUBLIC, authenticated;
REVOKE ALL ON FUNCTION public.agent_publish_message(text, text, text, text, text, text, jsonb, uuid) FROM PUBLIC, authenticated;
GRANT EXECUTE ON FUNCTION public.agent_heartbeat(text, text, text, text, text, text, jsonb, jsonb) TO anon;
GRANT EXECUTE ON FUNCTION public.agent_fetch_pending_commands(text, text, integer) TO anon;
GRANT EXECUTE ON FUNCTION public.agent_fetch_outbound_messages(text, text, integer) TO anon;
GRANT EXECUTE ON FUNCTION public.agent_update_command(text, text, uuid, text, jsonb, text, integer) TO anon;
GRANT EXECUTE ON FUNCTION public.agent_publish_message(text, text, text, text, text, text, jsonb, uuid) TO anon;