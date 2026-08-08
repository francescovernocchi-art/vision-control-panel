
CREATE TYPE public.app_role AS ENUM ('ADMIN','OPERATORE','DIREZIONE');

CREATE TABLE public.profiles (
  id uuid PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  email text,
  full_name text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
GRANT SELECT, INSERT, UPDATE, DELETE ON public.profiles TO authenticated;
GRANT ALL ON public.profiles TO service_role;
ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;

CREATE TABLE public.user_roles (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  role public.app_role NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (user_id, role)
);
GRANT SELECT ON public.user_roles TO authenticated;
GRANT ALL ON public.user_roles TO service_role;
ALTER TABLE public.user_roles ENABLE ROW LEVEL SECURITY;

CREATE OR REPLACE FUNCTION public.has_role(_user_id uuid, _role public.app_role)
RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
  SELECT EXISTS (SELECT 1 FROM public.user_roles WHERE user_id = _user_id AND role = _role)
$$;

CREATE OR REPLACE FUNCTION public.can_operate(_user_id uuid)
RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
  SELECT EXISTS (SELECT 1 FROM public.user_roles WHERE user_id = _user_id AND role IN ('ADMIN','OPERATORE'))
$$;

CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
BEGIN
  INSERT INTO public.profiles (id, email, full_name)
  VALUES (NEW.id, NEW.email, COALESCE(NEW.raw_user_meta_data->>'full_name', split_part(NEW.email,'@',1)))
  ON CONFLICT (id) DO NOTHING;
  INSERT INTO public.user_roles (user_id, role) VALUES (NEW.id, 'OPERATORE')
  ON CONFLICT DO NOTHING;
  RETURN NEW;
END; $$;

CREATE TRIGGER on_auth_user_created
AFTER INSERT ON auth.users FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();

CREATE POLICY "profiles readable by authenticated" ON public.profiles FOR SELECT TO authenticated USING (true);
CREATE POLICY "own profile update" ON public.profiles FOR UPDATE TO authenticated USING (id = auth.uid()) WITH CHECK (id = auth.uid());
CREATE POLICY "admin manage profiles" ON public.profiles FOR ALL TO authenticated USING (public.has_role(auth.uid(),'ADMIN')) WITH CHECK (public.has_role(auth.uid(),'ADMIN'));

CREATE POLICY "roles readable by authenticated" ON public.user_roles FOR SELECT TO authenticated USING (true);

CREATE TABLE public.devices (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  code text NOT NULL UNIQUE,
  name text NOT NULL,
  location text,
  status text NOT NULL DEFAULT 'OFFLINE',
  last_seen_at timestamptz,
  agent_version text,
  current_job_id uuid,
  heartbeat_threshold_seconds integer NOT NULL DEFAULT 120,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  is_demo boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
GRANT SELECT, INSERT, UPDATE, DELETE ON public.devices TO authenticated;
GRANT ALL ON public.devices TO service_role;
ALTER TABLE public.devices ENABLE ROW LEVEL SECURITY;
CREATE POLICY "devices read" ON public.devices FOR SELECT TO authenticated USING (true);
CREATE POLICY "devices admin" ON public.devices FOR ALL TO authenticated USING (public.has_role(auth.uid(),'ADMIN')) WITH CHECK (public.has_role(auth.uid(),'ADMIN'));

CREATE TABLE public.modules (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  key text NOT NULL UNIQUE,
  name text NOT NULL,
  description text,
  status text NOT NULL DEFAULT 'OFFLINE',
  enabled boolean NOT NULL DEFAULT true,
  last_activity_at timestamptz,
  current_job_id uuid,
  error_message text,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  is_demo boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
GRANT SELECT, INSERT, UPDATE, DELETE ON public.modules TO authenticated;
GRANT ALL ON public.modules TO service_role;
ALTER TABLE public.modules ENABLE ROW LEVEL SECURITY;
CREATE POLICY "modules read" ON public.modules FOR SELECT TO authenticated USING (true);
CREATE POLICY "modules admin" ON public.modules FOR ALL TO authenticated USING (public.has_role(auth.uid(),'ADMIN')) WITH CHECK (public.has_role(auth.uid(),'ADMIN'));

CREATE TABLE public.device_modules (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  device_id uuid NOT NULL REFERENCES public.devices(id) ON DELETE CASCADE,
  module_id uuid NOT NULL REFERENCES public.modules(id) ON DELETE CASCADE,
  status text NOT NULL DEFAULT 'OFFLINE',
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (device_id, module_id)
);
GRANT SELECT, INSERT, UPDATE, DELETE ON public.device_modules TO authenticated;
GRANT ALL ON public.device_modules TO service_role;
ALTER TABLE public.device_modules ENABLE ROW LEVEL SECURITY;
CREATE POLICY "device_modules read" ON public.device_modules FOR SELECT TO authenticated USING (true);
CREATE POLICY "device_modules admin" ON public.device_modules FOR ALL TO authenticated USING (public.has_role(auth.uid(),'ADMIN')) WITH CHECK (public.has_role(auth.uid(),'ADMIN'));

CREATE TABLE public.vision_jobs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  code text NOT NULL UNIQUE,
  module_id uuid REFERENCES public.modules(id) ON DELETE SET NULL,
  title text NOT NULL,
  source text,
  status text NOT NULL DEFAULT 'PENDING',
  progress integer NOT NULL DEFAULT 0,
  current_step text,
  started_at timestamptz,
  finished_at timestamptz,
  duration_seconds integer,
  operator_id uuid REFERENCES auth.users(id) ON DELETE SET NULL,
  device_id uuid REFERENCES public.devices(id) ON DELETE SET NULL,
  error text,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  is_demo boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
GRANT SELECT, INSERT, UPDATE, DELETE ON public.vision_jobs TO authenticated;
GRANT ALL ON public.vision_jobs TO service_role;
ALTER TABLE public.vision_jobs ENABLE ROW LEVEL SECURITY;
CREATE POLICY "jobs read" ON public.vision_jobs FOR SELECT TO authenticated USING (true);
CREATE POLICY "jobs admin" ON public.vision_jobs FOR ALL TO authenticated USING (public.has_role(auth.uid(),'ADMIN')) WITH CHECK (public.has_role(auth.uid(),'ADMIN'));

CREATE TABLE public.job_events (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  job_id uuid NOT NULL REFERENCES public.vision_jobs(id) ON DELETE CASCADE,
  event_type text NOT NULL,
  message text,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);
GRANT SELECT, INSERT, UPDATE, DELETE ON public.job_events TO authenticated;
GRANT ALL ON public.job_events TO service_role;
ALTER TABLE public.job_events ENABLE ROW LEVEL SECURITY;
CREATE POLICY "job_events read" ON public.job_events FOR SELECT TO authenticated USING (true);
CREATE POLICY "job_events admin" ON public.job_events FOR ALL TO authenticated USING (public.has_role(auth.uid(),'ADMIN')) WITH CHECK (public.has_role(auth.uid(),'ADMIN'));

CREATE TABLE public.commands (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  command_type text NOT NULL CHECK (command_type IN ('GET_STATUS','CHECK_ENISPACE_MAIL','RETRY_JOB','PAUSE_MODULE','RESUME_MODULE','PREPARE_COIN_TRANSPORT','APPROVE_JOB','REJECT_JOB')),
  module_id uuid REFERENCES public.modules(id) ON DELETE SET NULL,
  target_device_id uuid REFERENCES public.devices(id) ON DELETE SET NULL,
  job_id uuid REFERENCES public.vision_jobs(id) ON DELETE SET NULL,
  requested_by uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  requested_at timestamptz NOT NULL DEFAULT now(),
  status text NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING','ACKNOWLEDGED','EXECUTING','COMPLETED','FAILED','REJECTED')),
  parameters jsonb NOT NULL DEFAULT '{}'::jsonb,
  executed_at timestamptz,
  result jsonb,
  error text
);
GRANT SELECT, INSERT, UPDATE, DELETE ON public.commands TO authenticated;
GRANT ALL ON public.commands TO service_role;
ALTER TABLE public.commands ENABLE ROW LEVEL SECURITY;
CREATE POLICY "commands read" ON public.commands FOR SELECT TO authenticated USING (true);
CREATE POLICY "commands insert by operators" ON public.commands FOR INSERT TO authenticated
  WITH CHECK (public.can_operate(auth.uid()) AND requested_by = auth.uid() AND status = 'PENDING');
CREATE POLICY "commands admin" ON public.commands FOR ALL TO authenticated USING (public.has_role(auth.uid(),'ADMIN')) WITH CHECK (public.has_role(auth.uid(),'ADMIN'));

CREATE TABLE public.notifications (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  notification_type text NOT NULL,
  title text NOT NULL,
  message text,
  module_id uuid REFERENCES public.modules(id) ON DELETE SET NULL,
  job_id uuid REFERENCES public.vision_jobs(id) ON DELETE SET NULL,
  device_id uuid REFERENCES public.devices(id) ON DELETE SET NULL,
  user_id uuid REFERENCES auth.users(id) ON DELETE CASCADE,
  read_at timestamptz,
  is_demo boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now()
);
GRANT SELECT, INSERT, UPDATE, DELETE ON public.notifications TO authenticated;
GRANT ALL ON public.notifications TO service_role;
ALTER TABLE public.notifications ENABLE ROW LEVEL SECURITY;
CREATE POLICY "notifications read" ON public.notifications FOR SELECT TO authenticated USING (user_id IS NULL OR user_id = auth.uid());
CREATE POLICY "notifications update" ON public.notifications FOR UPDATE TO authenticated USING (user_id IS NULL OR user_id = auth.uid()) WITH CHECK (user_id IS NULL OR user_id = auth.uid());
CREATE POLICY "notifications admin" ON public.notifications FOR ALL TO authenticated USING (public.has_role(auth.uid(),'ADMIN')) WITH CHECK (public.has_role(auth.uid(),'ADMIN'));

CREATE TABLE public.approvals (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  job_id uuid REFERENCES public.vision_jobs(id) ON DELETE CASCADE,
  module_id uuid REFERENCES public.modules(id) ON DELETE SET NULL,
  title text NOT NULL,
  description text,
  status text NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING','APPROVED','REJECTED','CHANGES_REQUESTED','CANCELLED')),
  requested_at timestamptz NOT NULL DEFAULT now(),
  decided_at timestamptz,
  decided_by uuid REFERENCES auth.users(id) ON DELETE SET NULL,
  notes text,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  is_demo boolean NOT NULL DEFAULT false
);
GRANT SELECT, INSERT, UPDATE, DELETE ON public.approvals TO authenticated;
GRANT ALL ON public.approvals TO service_role;
ALTER TABLE public.approvals ENABLE ROW LEVEL SECURITY;
CREATE POLICY "approvals read" ON public.approvals FOR SELECT TO authenticated USING (true);
CREATE POLICY "approvals decide by operators" ON public.approvals FOR UPDATE TO authenticated
  USING (public.can_operate(auth.uid())) WITH CHECK (public.can_operate(auth.uid()));
CREATE POLICY "approvals admin" ON public.approvals FOR ALL TO authenticated USING (public.has_role(auth.uid(),'ADMIN')) WITH CHECK (public.has_role(auth.uid(),'ADMIN'));

CREATE TABLE public.audit_logs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid REFERENCES auth.users(id) ON DELETE SET NULL,
  action text NOT NULL,
  module_id uuid REFERENCES public.modules(id) ON DELETE SET NULL,
  job_id uuid REFERENCES public.vision_jobs(id) ON DELETE SET NULL,
  device_id uuid REFERENCES public.devices(id) ON DELETE SET NULL,
  ip_address text,
  outcome text NOT NULL DEFAULT 'OK',
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);
GRANT SELECT, INSERT ON public.audit_logs TO authenticated;
GRANT ALL ON public.audit_logs TO service_role;
ALTER TABLE public.audit_logs ENABLE ROW LEVEL SECURITY;
CREATE POLICY "audit read admin direzione" ON public.audit_logs FOR SELECT TO authenticated
  USING (public.has_role(auth.uid(),'ADMIN') OR public.has_role(auth.uid(),'DIREZIONE') OR user_id = auth.uid());
CREATE POLICY "audit insert own" ON public.audit_logs FOR INSERT TO authenticated WITH CHECK (user_id = auth.uid());

CREATE TABLE public.user_devices (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  endpoint text NOT NULL,
  p256dh text,
  auth_key text,
  user_agent text,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (user_id, endpoint)
);
GRANT SELECT, INSERT, UPDATE, DELETE ON public.user_devices TO authenticated;
GRANT ALL ON public.user_devices TO service_role;
ALTER TABLE public.user_devices ENABLE ROW LEVEL SECURITY;
CREATE POLICY "user_devices own" ON public.user_devices FOR ALL TO authenticated USING (user_id = auth.uid()) WITH CHECK (user_id = auth.uid());

ALTER TABLE public.devices REPLICA IDENTITY FULL;
ALTER TABLE public.modules REPLICA IDENTITY FULL;
ALTER TABLE public.vision_jobs REPLICA IDENTITY FULL;
ALTER TABLE public.job_events REPLICA IDENTITY FULL;
ALTER TABLE public.commands REPLICA IDENTITY FULL;
ALTER TABLE public.notifications REPLICA IDENTITY FULL;
ALTER TABLE public.approvals REPLICA IDENTITY FULL;
ALTER PUBLICATION supabase_realtime ADD TABLE public.devices, public.modules, public.vision_jobs, public.job_events, public.commands, public.notifications, public.approvals;

-- DEMO DATA (clearly flagged with is_demo = true)
INSERT INTO public.devices (id, code, name, location, status, last_seen_at, agent_version, is_demo)
VALUES ('11111111-1111-4111-8111-111111111111','VIS-TARANTO-01','Agent Taranto 01','Taranto','ONLINE', now() - interval '20 seconds','1.0', true);

INSERT INTO public.modules (id, key, name, description, status, last_activity_at, is_demo) VALUES
 ('22222222-2222-4222-8222-222222222221','enispace','eniSpace Automation','Controllo mail, download documenti e stampa ordini eniSpace','ONLINE', now() - interval '4 minutes', true),
 ('22222222-2222-4222-8222-222222222222','coin_transport','Trasporto Monete','Analisi mail Sala Conta, documenti trasporto e preparazione PEC','ONLINE', now() - interval '11 minutes', true);

INSERT INTO public.device_modules (device_id, module_id, status) VALUES
 ('11111111-1111-4111-8111-111111111111','22222222-2222-4222-8222-222222222221','ONLINE'),
 ('11111111-1111-4111-8111-111111111111','22222222-2222-4222-8222-222222222222','ONLINE');

INSERT INTO public.vision_jobs (id, code, module_id, title, source, status, progress, current_step, started_at, finished_at, duration_seconds, device_id, is_demo) VALUES
 ('33333333-3333-4333-8333-333333333331','VISION-2026-000128','22222222-2222-4222-8222-222222222221','Ordine eniSpace 4500123987','MAIL','PROCESSING',62,'DOWNLOAD', now() - interval '6 minutes', NULL, NULL,'11111111-1111-4111-8111-111111111111', true),
 ('33333333-3333-4333-8333-333333333332','VISION-2026-000127','22222222-2222-4222-8222-222222222222','Trasporto Monete TA / BR / LE','MAIL','WAITING_APPROVAL',85,'PEC', now() - interval '48 minutes', NULL, NULL,'11111111-1111-4111-8111-111111111111', true),
 ('33333333-3333-4333-8333-333333333333','VISION-2026-000126','22222222-2222-4222-8222-222222222221','Ordine eniSpace 4500123980','MAIL','COMPLETED',100,'DONE', now() - interval '3 hours', now() - interval '2 hours 52 minutes', 480,'11111111-1111-4111-8111-111111111111', true),
 ('33333333-3333-4333-8333-333333333334','VISION-2026-000125','22222222-2222-4222-8222-222222222221','Ordine eniSpace 4500123975','MAIL','FAILED',35,'LOGIN', now() - interval '5 hours', now() - interval '4 hours 58 minutes', 120,'11111111-1111-4111-8111-111111111111', true),
 ('33333333-3333-4333-8333-333333333335','VISION-2026-000129','22222222-2222-4222-8222-222222222222','Trasporto Monete BA','MAIL','QUEUED',0,NULL, NULL, NULL, NULL,'11111111-1111-4111-8111-111111111111', true);

UPDATE public.vision_jobs SET error = 'Login eniSpace non riuscito.' WHERE code = 'VISION-2026-000125';
UPDATE public.devices SET current_job_id = '33333333-3333-4333-8333-333333333331' WHERE code = 'VIS-TARANTO-01';
UPDATE public.modules SET current_job_id = '33333333-3333-4333-8333-333333333331' WHERE key = 'enispace';
UPDATE public.modules SET current_job_id = '33333333-3333-4333-8333-333333333332' WHERE key = 'coin_transport';

INSERT INTO public.job_events (job_id, event_type, message, created_at) VALUES
 ('33333333-3333-4333-8333-333333333331','MAIL_RECEIVED','Mail eniSpace rilevata', now() - interval '6 minutes'),
 ('33333333-3333-4333-8333-333333333331','ANALYSIS','Ordine 4500123987 identificato', now() - interval '5 minutes'),
 ('33333333-3333-4333-8333-333333333331','DOWNLOAD','Download 3 documenti in corso', now() - interval '2 minutes'),
 ('33333333-3333-4333-8333-333333333332','MAIL_RECEIVED','Mail Sala Conta acquisita', now() - interval '48 minutes'),
 ('33333333-3333-4333-8333-333333333332','PROCESSING','Riconosciuti 3 furgoni e itinerario TA / BR / LE', now() - interval '40 minutes'),
 ('33333333-3333-4333-8333-333333333332','WAITING_APPROVAL','PEC pronta per approvazione', now() - interval '35 minutes'),
 ('33333333-3333-4333-8333-333333333334','ERROR','Login eniSpace non riuscito.', now() - interval '4 hours 58 minutes');

INSERT INTO public.approvals (job_id, module_id, title, description, status, requested_at, metadata, is_demo) VALUES
 ('33333333-3333-4333-8333-333333333332','22222222-2222-4222-8222-222222222222','PEC pronta — Trasporto Monete','Documento di trasporto pronto per invio PEC. Province: TA / BR / LE.','PENDING', now() - interval '35 minutes','{"province":["TA","BR","LE"],"mezzi":3}'::jsonb, true);

INSERT INTO public.notifications (notification_type, title, message, module_id, job_id, created_at, is_demo) VALUES
 ('WAITING_APPROVAL','PEC in attesa di approvazione','Trasporto Monete: PEC pronta per TA / BR / LE','22222222-2222-4222-8222-222222222222','33333333-3333-4333-8333-333333333332', now() - interval '35 minutes', true),
 ('JOB_FAILED','Lavorazione fallita','VISION-2026-000125: Login eniSpace non riuscito.','22222222-2222-4222-8222-222222222221','33333333-3333-4333-8333-333333333334', now() - interval '4 hours 58 minutes', true),
 ('JOB_COMPLETED','Lavorazione completata','VISION-2026-000126 completata correttamente','22222222-2222-4222-8222-222222222221','33333333-3333-4333-8333-333333333333', now() - interval '2 hours 52 minutes', true);
