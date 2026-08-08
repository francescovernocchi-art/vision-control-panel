import { cn } from "@/lib/utils";
import { STATUS_TONE, toneClasses, type Tone } from "@/lib/vision";
import { statusLabel } from "@/lib/vision-status";

export function StatusDot({
  status,
  pulse = true,
  className,
}: {
  status: string;
  pulse?: boolean;
  className?: string;
}) {
  const tone: Tone = STATUS_TONE[status] ?? "muted";
  const color =
    tone === "success"
      ? "bg-success"
      : tone === "warning"
        ? "bg-warning"
        : tone === "danger"
          ? "bg-destructive"
          : tone === "info"
            ? "bg-info"
            : "bg-muted-foreground";
  return (
    <span
      aria-hidden
      className={cn(
        "inline-block size-2.5 shrink-0 rounded-full",
        color,
        pulse && tone !== "muted" && "pulse-dot",
        className,
      )}
    />
  );
}

export function StatusBadge({
  status,
  tone,
  className,
}: {
  status: string;
  tone?: Tone;
  className?: string;
}) {
  const resolved: Tone = tone ?? STATUS_TONE[status] ?? "muted";
  const label = statusLabel(status);
  return (
    <span
      role="status"
      aria-label={label}
      title={label}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-md border px-2 py-0.5 font-mono text-[0.65rem] tracking-widest uppercase",
        toneClasses(resolved),
        className,
      )}
    >
      <StatusDot status={status} pulse={false} className="size-1.5" />
      <span>{status}</span>
    </span>
  );
}
