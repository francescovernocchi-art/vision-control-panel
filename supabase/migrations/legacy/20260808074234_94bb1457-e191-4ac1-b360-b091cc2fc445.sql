CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path TO 'public'
AS $function$
BEGIN
  INSERT INTO public.profiles (id, email, full_name)
  VALUES (NEW.id, NEW.email, COALESCE(NEW.raw_user_meta_data->>'full_name', split_part(NEW.email,'@',1)))
  ON CONFLICT (id) DO NOTHING;

  IF lower(NEW.email) = 'francesco.vernocchi@visvigilanza.net' THEN
    INSERT INTO public.user_roles (user_id, role) VALUES (NEW.id, 'ADMIN')
    ON CONFLICT DO NOTHING;
  ELSE
    INSERT INTO public.user_roles (user_id, role) VALUES (NEW.id, 'OPERATORE')
    ON CONFLICT DO NOTHING;
  END IF;

  RETURN NEW;
END; $function$;

INSERT INTO public.user_roles (user_id, role)
SELECT id, 'ADMIN'::app_role FROM auth.users
WHERE lower(email) = 'francesco.vernocchi@visvigilanza.net'
ON CONFLICT DO NOTHING;