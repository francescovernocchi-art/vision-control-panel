import { useQuery, useQueryClient } from "@tanstack/react-query";

import { supabase } from "@/integrations/supabase/client";

export interface BootstrapState {
  /** Email configured as ADMIN, or null when the app is not configured yet. */
  adminEmail: string | null;
  /** True when at least one ADMIN role row exists. */
  adminExists: boolean;
  configured: boolean;
  loading: boolean;
}

/** Reads the initial-setup configuration (which email becomes ADMIN). */
export function useBootstrap(): BootstrapState {
  const query = useQuery({
    queryKey: ["app_bootstrap"],
    queryFn: async () => {
      const [{ data: cfg, error }, { data: adminFlag, error: e2 }] = await Promise.all([
        (supabase.from("app_bootstrap" as any).select("*").limit(1).maybeSingle() as any),
        // RLS hides other users' roles, so ask the database directly.
        supabase.rpc("admin_exists"),
      ]);
      if (error) throw error;
      if (e2) throw e2;
      return {
        adminEmail: (cfg?.admin_email as string | null) ?? null,
        adminExists: adminFlag === true,
      };

    },
  });

  const adminEmail = query.data?.adminEmail ?? null;
  const adminExists = query.data?.adminExists ?? false;
  return {
    adminEmail,
    adminExists,
    configured: !!adminEmail,
    loading: query.isLoading,
  };
}

/**
 * Saves the ADMIN email. The database applies the role automatically:
 * immediately if that user already exists, otherwise at their first signup.
 */
export async function saveAdminEmail(email: string) {
  const clean = email.trim().toLowerCase();
  const { data: existing } = (await supabase
    .from("app_bootstrap" as any)
    .select("id")
    .limit(1)
    .maybeSingle()) as any;

  if (existing?.id) {
    const { error } = await (supabase.from("app_bootstrap" as any) as any)
      .update({ admin_email: clean })
      .eq("id", existing.id);
    if (error) throw error;
  } else {
    const { error } = await (supabase.from("app_bootstrap" as any) as any).insert({
      admin_email: clean,
    });
    if (error) throw error;
  }
  return clean;
}

export function useInvalidateBootstrap() {
  const qc = useQueryClient();
  return () => {
    void qc.invalidateQueries({ queryKey: ["app_bootstrap"] });
    void qc.invalidateQueries({ queryKey: ["my_roles"] });
    void qc.invalidateQueries({ queryKey: ["user_roles"] });
  };
}
