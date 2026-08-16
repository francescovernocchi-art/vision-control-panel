import accesso from "@/assets/supervisor/accesso.png";
import analisi from "@/assets/supervisor/analisi.png";
import completato from "@/assets/supervisor/completato.png";
import download from "@/assets/supervisor/download.png";
import errore from "@/assets/supervisor/errore.png";
import idle from "@/assets/supervisor/idle.png";
import intervento from "@/assets/supervisor/intervento.png";
import mail from "@/assets/supervisor/mail.png";
import stampa from "@/assets/supervisor/stampa.png";
import { cn } from "@/lib/utils";
import { SUPERVISOR_LABEL, type SupervisorState } from "@/lib/vision";

/** Same frame set the desktop Agent uses, so PWA and Agent show one avatar. */
const STATE_FRAME: Record<SupervisorState, string> = {
  IDLE: idle,
  MAIL_RECEIVED: mail,
  ANALYSIS: analisi,
  PROCESSING: accesso,
  DOWNLOAD: download,
  PRINTING: stampa,
  WAITING_APPROVAL: intervento,
  SUCCESS: completato,
  ERROR: errore,
  NEEDS_ATTENTION: intervento,
};

const STATE_RING: Record<SupervisorState, string> = {
  IDLE: "ring-muted-foreground/40",
  MAIL_RECEIVED: "ring-info/60",
  ANALYSIS: "ring-info/60",
  PROCESSING: "ring-primary/70",
  DOWNLOAD: "ring-primary/70",
  PRINTING: "ring-accent/70",
  WAITING_APPROVAL: "ring-warning/70",
  SUCCESS: "ring-success/70",
  ERROR: "ring-destructive/70",
  NEEDS_ATTENTION: "ring-warning/70",
};

/**
 * Decorative avatar. The ring/scanline reacts to the supervisor state so a
 * future animated asset can be swapped in without touching call sites.
 */
export function SupervisorAvatar({
  state,
  size = 132,
  className,
}: {
  state: SupervisorState;
  size?: number;
  className?: string;
}) {
  const animated = ["PROCESSING", "DOWNLOAD", "ANALYSIS", "PRINTING"].includes(state);
  return (
    <div
      className={cn(
        "relative shrink-0 overflow-hidden rounded-2xl ring-2 ring-offset-2 ring-offset-background",
        STATE_RING[state],
        animated && "glow-accent",
        className,
      )}
      style={{ width: size, height: size }}
      aria-label={`VISION Supervisor — ${SUPERVISOR_LABEL[state]}`}
    >
      <img
        src={STATE_FRAME[state]}
        alt="Avatar VISION Supervisor"
        width={size}
        height={size}
        loading="lazy"
        className="size-full object-cover"
      />
      {animated && (
        <div className="pointer-events-none absolute inset-0">
          <div className="scanline h-1/3 w-full bg-gradient-to-b from-transparent via-accent/25 to-transparent" />
        </div>
      )}
    </div>
  );
}
