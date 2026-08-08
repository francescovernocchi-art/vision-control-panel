import { createFileRoute, Link } from "@tanstack/react-router";
import { useState } from "react";
import { Search } from "lucide-react";

import { AppShell } from "@/components/vision/AppShell";
import { StatusBadge } from "@/components/vision/StatusBadge";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { formatDateTime, formatDuration } from "@/lib/vision";
import { useDevices, useJobs, useModules, useProfiles } from "@/lib/vision-data";

export const Route = createFileRoute("/_authenticated/lavorazioni")({
  head: () => ({
    meta: [
      { title: "Lavorazioni — VIS•ION" },
      { name: "description", content: "Coda e storico delle lavorazioni VIS•ION." },
      { name: "robots", content: "noindex, nofollow" },
      { property: "og:title", content: "Lavorazioni — VIS•ION" },
      { property: "og:description", content: "Coda e storico lavorazioni VIS•ION." },
    ],
  }),
  component: JobsPage,
});

const STATUSES = [
  "PENDING",
  "QUEUED",
  "PROCESSING",
  "WAITING_APPROVAL",
  "COMPLETED",
  "PARTIAL",
  "NEEDS_ATTENTION",
  "FAILED",
  "CANCELLED",
];

function JobsPage() {
  const { data: jobs = [] } = useJobs();
  const { data: modules = [] } = useModules();
  const { data: devices = [] } = useDevices();
  const { data: profiles = [] } = useProfiles();

  const [moduleId, setModuleId] = useState("all");
  const [status, setStatus] = useState("all");
  const [day, setDay] = useState("");
  const [search, setSearch] = useState("");

  const filtered = jobs.filter((j: any) => {
    if (moduleId !== "all" && j.module_id !== moduleId) return false;
    if (status !== "all" && j.status !== status) return false;
    if (day && new Date(j.created_at).toISOString().slice(0, 10) !== day) return false;
    if (search) {
      const s = search.toLowerCase();
      if (!`${j.code} ${j.title}`.toLowerCase().includes(s)) return false;
    }
    return true;
  });

  const nameOf = (id: string | null) =>
    profiles.find((p: any) => p.id === id)?.full_name ?? "—";

  return (
    <AppShell title="Lavorazioni" subtitle={`${filtered.length} risultati`}>
      <div className="space-y-4">
        <div className="hud-panel grid gap-2 p-3 sm:grid-cols-2 lg:grid-cols-4">
          <Select value={moduleId} onValueChange={setModuleId}>
            <SelectTrigger>
              <SelectValue placeholder="Modulo" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Tutti i moduli</SelectItem>
              {modules.map((m: any) => (
                <SelectItem key={m.id} value={m.id}>
                  {m.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select value={status} onValueChange={setStatus}>
            <SelectTrigger>
              <SelectValue placeholder="Stato" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Tutti gli stati</SelectItem>
              {STATUSES.map((s) => (
                <SelectItem key={s} value={s}>
                  {s}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Input type="date" value={day} onChange={(e) => setDay(e.target.value)} />
          <div className="relative">
            <Search className="absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              className="pl-8"
              placeholder="Cerca ID o titolo"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
        </div>

        <ul className="space-y-2">
          {filtered.map((j: any) => (
            <li key={j.id}>
              <Link
                to="/jobs/$id"
                params={{ id: j.id }}
                className="hud-panel block space-y-2 p-3 transition-colors hover:border-accent/50"
              >
                <div className="grid grid-cols-[minmax(0,1fr)_auto] items-start gap-3">
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium">{j.title}</p>
                    <p className="truncate font-mono text-[0.65rem] text-muted-foreground">
                      {j.code} · {modules.find((m: any) => m.id === j.module_id)?.name ?? "—"}
                    </p>
                  </div>
                  <StatusBadge status={j.status} />
                </div>
                <Progress value={j.progress ?? 0} className="h-1.5" />
                <div className="grid grid-cols-2 gap-2 text-[0.65rem] text-muted-foreground sm:grid-cols-4">
                  <span>{formatDateTime(j.created_at)}</span>
                  <span>Durata: {formatDuration(j.duration_seconds)}</span>
                  <span className="truncate">Operatore: {nameOf(j.operator_id)}</span>
                  <span className="truncate">
                    Device: {devices.find((d: any) => d.id === j.device_id)?.code ?? "—"}
                  </span>
                </div>
              </Link>
            </li>
          ))}
          {filtered.length === 0 && (
            <li className="hud-panel p-6 text-center text-sm text-muted-foreground">
              Nessuna lavorazione corrisponde ai filtri.
            </li>
          )}
        </ul>
      </div>
    </AppShell>
  );
}
