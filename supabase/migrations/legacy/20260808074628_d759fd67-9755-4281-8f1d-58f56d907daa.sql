CREATE TABLE public.app_bootstrap (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  singleton boolean NOT NULL DEFAULT true UNIQUE,
  admin_email text,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  updated_at timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT app_bootstrap_singleton_true CHECK (singleton = true)
);

GRANT SELECT, INSERT, UPDATE ON public.app_bootstrap TO authenticated;
GRANT ALL ON public.app_bootstrap TO service_role;

ALTER TABLE public.app_bootstrap ENABLE ROW LEVEL SECURITY;

CREATE OR REPLACE FUNCTION public.admin_exists()
RETURNS boolean
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
  SELECT EXISTS (SELECT 1 FROM public.user_roles WHERE role = 'ADMIN')
$$;

CREATE POLICY "bootstrap read" ON public.app_bootstrap
FOR SELECT TO authenticated USING (true);

CREATE POLICY "bootstrap insert while unclaimed or admin" ON public.app_bootstrap
FOR INSERT TO authenticated
WITH CHECK ((NOT public.admin_exists()) OR public.has_role(auth.uid(), 'ADMIN'));

CREATE POLICY "bootstrap update while unclaimed or admin" ON public.app_bootstrap
FOR UPDATE TO authenticated
USING ((NOT public.admin_exists()) OR public.has_role(auth.uid(), 'ADMIN'))
WITH CHECK ((NOT public.admin_exists()) OR public.has_role(auth.uid(), 'ADMIN'));

CREATE OR REPLACE FUNCTION public.set_updated_at()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = public
AS $$ BEGIN NEW.updated_at = now(); RETURN NEW; END; $$;

CREATE TRIGGER update_app_bootstrap_updated_at
BEFORE UPDATE ON public.app_bootstrap
FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- Promote the configured email immediately if that user already signed up
CREATE OR REPLACE FUNCTION public.apply_bootstrap_admin()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  IF NEW.admin_email IS NOT NULL THEN
    INSERT INTO public.user_roles (user_id, role)
    SELECT u.id, 'ADMIN'::app_role FROM auth.users u
    WHERE lower(u.email) = lower(NEW.admin_email)
    ON CONFLICT DO NOTHING;
  END IF;
  RETURN NEW;
END; $$;

CREATE TRIGGER app_bootstrap_apply_admin
AFTER INSERT OR UPDATE OF admin_email ON public.app_bootstrap
FOR EACH ROW EXECUTE FUNCTION public.apply_bootstrap_admin();

-- New signups read the configured admin email
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  bootstrap_email text;
BEGIN
  INSERT INTO public.profiles (id, email, full_name)
  VALUES (NEW.id, NEW.email, COALESCE(NEW.raw_user_meta_data->>'full_name', split_part(NEW.email,'@',1)))
  ON CONFLICT (id) DO NOTHING;

  SELECT admin_email INTO bootstrap_email FROM public.app_bootstrap LIMIT 1;

  IF bootstrap_email IS NOT NULL AND lower(NEW.email) = lower(bootstrap_email) THEN
    INSERT INTO public.user_roles (user_id, role) VALUES (NEW.id, 'ADMIN')
    ON CONFLICT DO NOTHING;
  ELSE
    INSERT INTO public.user_roles (user_id, role) VALUES (NEW.id, 'OPERATORE')
    ON CONFLICT DO NOTHING;
  END IF;

  RETURN NEW;
END; $$;

INSERT INTO public.app_bootstrap (admin_email) VALUES ('francesco.vernocchi@visvigilanza.net');
