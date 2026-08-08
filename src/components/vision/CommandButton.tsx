import { useEffect, useState, type ReactNode } from "react";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useOnlineStatus } from "@/hooks/useAuth";

export interface ConfirmDetail {
  label: string;
  value: string;
}

/**
 * Command button with an explicit second confirmation for sensitive actions
 * and a hard block when the phone has no connectivity.
 *
 * For critical actions pass `confirmKeyword`: the dialog then shows a detailed
 * summary and the action stays blocked until the exact keyword is typed.
 */
export function CommandButton({
  label,
  description,
  details,
  confirmKeyword,
  confirmLabel,
  onConfirm,
  sensitive = false,
  disabled = false,
  disabledReason,
  variant = "secondary",
  size = "sm",
  icon,
  className,
}: {
  label: string;
  description?: string | undefined;
  details?: ConfirmDetail[] | undefined;
  confirmKeyword?: string | undefined;
  confirmLabel?: string | undefined;
  onConfirm: () => Promise<void> | void;
  sensitive?: boolean;
  disabled?: boolean;
  disabledReason?: string | undefined;
  variant?: "default" | "secondary" | "destructive" | "outline" | "ghost";
  size?: "sm" | "default" | "lg";
  icon?: ReactNode | undefined;
  className?: string | undefined;
}) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [typed, setTyped] = useState("");
  const online = useOnlineStatus();

  // Reset the typed keyword every time the dialog opens or closes: a previous
  // confirmation must never carry over to the next one.
  useEffect(() => {
    if (!open) setTyped("");
  }, [open]);

  const blocked = disabled || !online;
  const reason = !online
    ? "Nessuna connessione: impossibile inviare comandi."
    : disabledReason;

  const keywordOk =
    !confirmKeyword || typed.trim().toUpperCase() === confirmKeyword.toUpperCase();

  async function run() {
    // Hard block: never execute unless the confirmation was completed.
    if (!keywordOk || busy) return;
    setBusy(true);
    try {
      await onConfirm();
    } finally {
      setBusy(false);
      setOpen(false);
      setTyped("");
    }
  }

  return (
    <>
      <Button
        variant={variant}
        size={size}
        className={className}
        disabled={blocked || busy}
        title={blocked ? reason : undefined}
        onClick={() => (sensitive ? setOpen(true) : void run())}
      >
        {icon}
        {label}
      </Button>
      <AlertDialog open={open} onOpenChange={(v) => !busy && setOpen(v)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Conferma operazione — {label}</AlertDialogTitle>
            <AlertDialogDescription>
              {description ??
                `Confermi l'esecuzione di "${label}"? L'operazione verrà inviata al VIS•ION Core.`}
            </AlertDialogDescription>
          </AlertDialogHeader>

          {details && details.length > 0 && (
            <dl className="space-y-1.5 rounded-lg border border-border bg-muted/30 p-3 text-xs">
              {details.map((d) => (
                <div key={d.label} className="grid grid-cols-[8rem_minmax(0,1fr)] gap-2">
                  <dt className="text-muted-foreground">{d.label}</dt>
                  <dd className="break-words font-mono">{d.value}</dd>
                </div>
              ))}
            </dl>
          )}

          {confirmKeyword && (
            <div className="space-y-1.5">
              <Label htmlFor="confirm-keyword" className="text-xs">
                Per procedere digita{" "}
                <span className="font-mono font-bold text-accent">{confirmKeyword}</span>
              </Label>
              <Input
                id="confirm-keyword"
                autoComplete="off"
                autoCapitalize="characters"
                value={typed}
                placeholder={confirmKeyword}
                onChange={(e) => setTyped(e.target.value)}
              />
              {!keywordOk && typed.length > 0 && (
                <p className="text-[0.65rem] text-destructive">
                  Testo non corrispondente: l'operazione resta bloccata.
                </p>
              )}
            </div>
          )}

          <AlertDialogFooter>
            <AlertDialogCancel disabled={busy}>Annulla</AlertDialogCancel>
            <AlertDialogAction
              disabled={busy || !keywordOk}
              onClick={(e) => {
                e.preventDefault();
                void run();
              }}
            >
              {busy ? "Invio…" : (confirmLabel ?? "Conferma")}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
