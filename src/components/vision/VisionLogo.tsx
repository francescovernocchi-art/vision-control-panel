import logo from "@/assets/vision-logo.png";
import { cn } from "@/lib/utils";

export function VisionLogo({
  size = 36,
  className,
}: {
  size?: number;
  className?: string;
}) {
  return (
    <img
      src={logo}
      alt="Logo VIS•ION"
      width={size}
      height={size}
      loading="lazy"
      className={cn("rounded-lg object-contain", className)}
      style={{ width: size, height: size }}
    />
  );
}

export function VisionWordmark({ compact = false }: { compact?: boolean }) {
  return (
    <div className="flex min-w-0 items-center gap-2.5">
      <VisionLogo size={compact ? 28 : 36} className="shrink-0" />
      <div className="min-w-0">
        <p className="truncate font-mono text-sm font-bold tracking-[0.22em] text-foreground">
          VIS•ION
        </p>
        {!compact && (
          <p className="truncate text-[0.65rem] text-muted-foreground">
            VIS Intelligent Operations Network
          </p>
        )}
      </div>
    </div>
  );
}
