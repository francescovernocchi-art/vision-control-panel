import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import type { Session } from "@supabase/supabase-js";

import { supabase } from "@/integrations/supabase/client";
import type { AppRole } from "@/lib/vision";

export function useSession() {
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const { data: sub } = supabase.auth.onAuthStateChange((_event, next) => {
      setSession(next);
      setLoading(false);
    });
    void supabase.auth.getSession().then(({ data }) => {
      setSession(data.session);
      setLoading(false);
    });
    return () => sub.subscription.unsubscribe();
  }, []);

  return { session, user: session?.user ?? null, loading };
}

export function useRoles() {
  const { user } = useSession();
  const query = useQuery({
    queryKey: ["my_roles", user?.id],
    enabled: !!user,
    queryFn: async () => {
      // Canonical Agent schema: profiles.role (column may be absent on legacy DB)
      const profile = await supabase
        .from("profiles")
        .select("*")
        .eq("user_id" as never, user!.id)
        .maybeSingle();
      const profileRole = (profile.data as { role?: AppRole } | null)?.role;
      if (!profile.error && profileRole) {
        return [profileRole];
      }
      // Legacy Lovable: user_roles table
      const { data, error } = await supabase
        .from("user_roles")
        .select("role")
        .eq("user_id", user!.id);
      if (error) throw error;
      return (data ?? []).map((r) => r.role as AppRole);
    },
  });

  const roles = query.data ?? [];
  return {
    roles,
    loading: query.isLoading,
    isAdmin: roles.includes("ADMIN"),
    isOperatore: roles.includes("OPERATORE"),
    isDirezione: roles.includes("DIREZIONE"),
    canOperate: roles.includes("ADMIN") || roles.includes("OPERATORE"),
    hasAny: (allowed: AppRole[]) => roles.some((r) => allowed.includes(r)),
  };
}

export function useProfile() {
  const { user } = useSession();
  return useQuery({
    queryKey: ["my_profile", user?.id],
    enabled: !!user,
    queryFn: async () => {
      // Canonical: profiles.user_id; legacy Lovable: profiles.id
      const byUserId = await supabase
        .from("profiles")
        .select("*")
        .eq("user_id" as never, user!.id)
        .maybeSingle();
      if (!byUserId.error && byUserId.data) return byUserId.data;
      const { data, error } = await supabase
        .from("profiles")
        .select("*")
        .eq("id", user!.id)
        .maybeSingle();
      if (error) throw error;
      return data;
    },
  });
}

export function useOnlineStatus() {
  const [online, setOnline] = useState(true);
  useEffect(() => {
    setOnline(navigator.onLine);
    const on = () => setOnline(true);
    const off = () => setOnline(false);
    window.addEventListener("online", on);
    window.addEventListener("offline", off);
    return () => {
      window.removeEventListener("online", on);
      window.removeEventListener("offline", off);
    };
  }, []);
  return online;
}
