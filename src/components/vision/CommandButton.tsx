import { useState, type ReactNode } from "react";
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
import { useOnlineStatus } from "@/hooks/useAuth";

/**
 * Command button with an explicit second confirmation for sensitive actions
 * and a hard block when the phone has no connectivity.
 */
export function CommandButton({
  label,
  description,
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
  const online = useOnlineStatus();

  const blocked = disabled || !online;
  const reason = !online
    ? "Nessuna connessione: impossibile inviare comandi."
    : disabledReason;

  async function run() {
    setBusy(true);
    try {
      await onConfirm();
    } finally {
      setBusy(false);
      setOpen(false);
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
      <AlertDialog open={open} onOpenChange={setOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Conferma operazione</AlertDialogTitle>
            <AlertDialogDescription>
              {description ??
                `Confermi l'esecuzione di "${label}"? L'operazione verrà inviata al VIS•ION Core.`}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Annulla</AlertDialogCancel>
            <AlertDialogAction disabled={busy} onClick={(e) => { e.preventDefault(); void run(); }}>
              Conferma
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
