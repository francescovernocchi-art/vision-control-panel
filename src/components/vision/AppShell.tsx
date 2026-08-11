import { Link, useNavigate, useRouterState } from "@tanstack/react-router";
import {
  Activity,
  BellRing,
  BadgeCheck,
  Cpu,
  Download,
  LayoutDashboard,
  ListChecks,
  LogOut,
  Menu,
  MessageSquare,
  ScrollText,
  Settings,
  ShieldCheck,
  User,
  WifiOff,
} from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { StatusDot } from "@/components/vision/StatusBadge";
import { VisionWordmark } from "@/components/vision/VisionLogo";
import { useOnlineStatus, useProfile, useRoles } from "@/hooks/useAuth";
import { usePwaInstall } from "@/hooks/usePwaInstall";
import { supabase } from "@/integrations/supabase/client";
import { cn } from "@/lib/utils";
import { logAudit, useDevices, useNotifications, useVisionRealtime } from "@/lib/vision-data";
import { useBootstrap } from "@/lib/vision-bootstrap";
import { isDeviceOnline } from "@/lib/vision";


const NAV = [
  { to: "/chat", label: "Chat Supervisor", icon: MessageSquare },
  { to: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { to: "/attivita", label: "Attività", icon: Activity },
  { to: "/moduli", label: "Moduli", icon: Cpu },
  { to: "/lavorazioni", label: "Lavorazioni", icon: ListChecks },
  { to: "/notifiche", label: "Notifiche", icon: BellRing },
  { to: "/approvazioni", label: "Approvazioni", icon: BadgeCheck },
  { to: "/dispositivi", label: "Dispositivi", icon: Activity },
  { to: "/audit", label: "Audit", icon: ScrollText },
  { to: "/impostazioni", label: "Impostazioni", icon: Settings },
  { to: "/profilo", label: "Profilo", icon: User },
] as const;

const MOBILE_NAV = NAV.slice(0, 4);

export function AppShell({
  title,
  subtitle,
  actions,
  children,
}: {
  title: string;
  subtitle?: string;
  actions?: ReactNode;
  children: ReactNode;
}) {
  const pathname = useRouterState({ select: (s) => s.location.pathname });
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const online = useOnlineStatus();
  const { roles } = useRoles();
  const { data: profile } = useProfile();
  const { canInstall, install } = usePwaInstall();
  const bootstrap = useBootstrap();
  const [menuOpen, setMenuOpen] = useState(false);


  const realtime = useVisionRealtime([
    "devices",
    "modules",
    "vision_jobs",
    "job_events",
    "commands",
    "notifications",
    "approvals",
    "agent_messages",
  ]);
  const liveStatus = !online ? "OFFLINE" : realtime === "LIVE" ? "ONLINE" : "PENDING";


  const { data: devices = [] } = useDevices();
  const { data: notifications = [] } = useNotifications();
  const unread = notifications.filter((n: any) => !n.read_at).length;
  const anyDeviceOnline = devices.some((d: any) =>
    isDeviceOnline(d.last_seen_at, d.heartbeat_threshold_seconds ?? 120),
  );

  async function signOut() {
    await logAudit({ action: "LOGOUT" });
    await queryClient.cancelQueries();
    queryClient.clear();
    await supabase.auth.signOut();
    void navigate({ to: "/auth", replace: true });
  }

  const navList = (compact = false) => (
    <nav className="flex flex-col gap-1">
      {NAV.map((item) => {
        const active = pathname === item.to || pathname.startsWith(`${item.to}/`);
        return (
          <Link
            key={item.to}
            to={item.to}
            onClick={() => setMenuOpen(false)}
            className={cn(
              "flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors",
              active
                ? "bg-sidebar-accent text-sidebar-primary"
                : "text-sidebar-foreground/75 hover:bg-sidebar-accent/60 hover:text-sidebar-foreground",
            )}
          >
            <item.icon className="size-4 shrink-0" />
            <span className="truncate">{item.label}</span>
            {item.to === "/notifiche" && unread > 0 && (
              <span className="ml-auto rounded-full bg-accent px-1.5 py-0.5 font-mono text-[0.6rem] text-accent-foreground">
                {unread}
              </span>
            )}
          </Link>
        );
      })}
      {!compact && (
        <button
          onClick={() => void signOut()}
          className="mt-1 flex items-center gap-3 rounded-lg px-3 py-2 text-sm text-sidebar-foreground/75 transition-colors hover:bg-destructive/15 hover:text-destructive"
        >
          <LogOut className="size-4 shrink-0" />
          Logout
        </button>
      )}
    </nav>
  );

  return (
    <div className="flex min-h-screen w-full">
      <aside className="hidden w-64 shrink-0 flex-col border-r border-sidebar-border bg-sidebar p-4 lg:flex">
        <div className="px-1 pb-5">
          <VisionWordmark />
        </div>
        {navList()}
        <div className="mt-auto space-y-2 pt-4">
          {canInstall && (
            <Button variant="outline" size="sm" className="w-full" onClick={() => void install()}>
              <Download className="size-4" /> Installa VIS•ION
            </Button>
          )}
          <div className="rounded-lg border border-sidebar-border p-3">
            <p className="hud-title">Sessione</p>
            <p className="mt-1 truncate text-xs text-sidebar-foreground">
              {profile?.full_name ?? profile?.email ?? "—"}
            </p>
            <p className="mt-1 font-mono text-[0.6rem] tracking-widest text-accent">
              {roles.join(" · ") || "NESSUN RUOLO"}
            </p>
          </div>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 border-b border-border bg-background/85 backdrop-blur">
          <div className="grid grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-3 px-4 py-3">
            <Sheet open={menuOpen} onOpenChange={setMenuOpen}>
              <SheetTrigger asChild>
                <Button variant="ghost" size="icon" className="lg:hidden">
                  <Menu className="size-5" />
                </Button>
              </SheetTrigger>
              <SheetContent side="left" className="w-72 bg-sidebar p-4">
                <SheetTitle className="sr-only">Menu VIS•ION</SheetTitle>
                <div className="pb-5">
                  <VisionWordmark />
                </div>
                {navList()}
              </SheetContent>
            </Sheet>
            <div className="min-w-0">
              <h1 className="truncate text-base font-semibold tracking-tight sm:text-lg">{title}</h1>
              {subtitle && (
                <p className="truncate text-xs text-muted-foreground">{subtitle}</p>
              )}
            </div>
            <div className="flex items-center gap-2">
              {actions}
              <div className="hidden items-center gap-3 rounded-lg border border-border px-3 py-1.5 sm:flex">
                <span className="flex items-center gap-1.5 font-mono text-[0.6rem] tracking-widest">
                  <StatusDot status={online ? "ONLINE" : "OFFLINE"} /> CLOUD
                </span>
                <span
                  className="flex items-center gap-1.5 font-mono text-[0.6rem] tracking-widest"
                  title={
                    realtime === "LIVE"
                      ? "Aggiornamenti realtime attivi"
                      : "Stream realtime non attivo: riconnessione in corso"
                  }
                >
                  <StatusDot status={liveStatus} /> LIVE
                </span>
                <span className="flex items-center gap-1.5 font-mono text-[0.6rem] tracking-widest">
                  <StatusDot status={anyDeviceOnline ? "ONLINE" : "OFFLINE"} /> AGENT
                </span>
              </div>

            </div>
          </div>
          {!bootstrap.loading && !bootstrap.configured && pathname !== "/setup" && (
            <Link
              to="/setup"
              className="flex items-center gap-2 border-t border-accent/40 bg-accent/10 px-4 py-2 text-xs text-accent"
            >
              <ShieldCheck className="size-4 shrink-0" />
              Configurazione iniziale non completata: seleziona l'email amministratore →
            </Link>
          )}
          {!online && (
            <div className="flex items-center gap-2 border-t border-destructive/40 bg-destructive/15 px-4 py-2 text-xs text-destructive">
              <WifiOff className="size-4 shrink-0" />
              Modalità offline: i dati potrebbero non essere aggiornati e i comandi sono
              disabilitati.
            </div>
          )}

        </header>

        <main className="flex-1 px-4 pt-4 pb-24 lg:pb-8">{children}</main>

        <nav className="fixed inset-x-0 bottom-0 z-30 grid grid-cols-5 border-t border-border bg-background/95 backdrop-blur lg:hidden">
          {MOBILE_NAV.map((item) => {
            const active = pathname === item.to || pathname.startsWith(`${item.to}/`);
            return (
              <Link
                key={item.to}
                to={item.to}
                className={cn(
                  "flex flex-col items-center gap-1 py-2.5 text-[0.6rem]",
                  active ? "text-accent" : "text-muted-foreground",
                )}
              >
                <item.icon className="size-5" />
                {item.label}
              </Link>
            );
          })}
          <button
            onClick={() => setMenuOpen(true)}
            className="relative flex flex-col items-center gap-1 py-2.5 text-[0.6rem] text-muted-foreground"
          >
            <ShieldCheck className="size-5" />
            Altro
            {unread > 0 && (
              <span className="absolute top-1.5 right-1/4 size-2 rounded-full bg-accent" />
            )}
          </button>
        </nav>
      </div>
    </div>
  );
}
