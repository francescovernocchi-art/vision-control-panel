import { ChevronDown, Play, Terminal, Type } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { filterChatCommands, type ChatCommand } from "@/lib/vision-chat-commands";

/**
 * Pannello "/comandi": elenca i comandi strutturati (eseguibili) e le frasi
 * interpretate dal Supervisor (inserite nel composer).
 */
export function ChatCommandPalette({
  query,
  onPick,
  onClose,
  canOperate,
  className,
}: {
  query: string;
  onPick: (command: ChatCommand) => void;
  onClose: () => void;
  canOperate: boolean;
  className?: string;
}) {
  const results = filterChatCommands(query);
  const actions = results.filter((c) => c.kind === "action");
  const phrases = results.filter((c) => c.kind === "phrase");

  return (
    <div
      className={cn(
        "max-h-[46vh] overflow-y-auto rounded-xl border border-border/80 bg-card/95 p-2 backdrop-blur",
        className,
      )}
    >
      <div className="mb-1 flex items-center justify-between px-1">
        <p className="font-mono text-[0.6rem] tracking-widest text-muted-foreground uppercase">
          Comandi chat
        </p>
        <Button
          variant="ghost"
          size="icon"
          className="size-7"
          onClick={onClose}
          aria-label="Chiudi lista comandi"
        >
          <ChevronDown className="size-4" />
        </Button>
      </div>

      {results.length === 0 && (
        <p className="px-2 py-3 text-xs text-muted-foreground">Nessun comando trovato.</p>
      )}

      {actions.length > 0 && (
        <Section title="Comandi Agent" icon={<Terminal className="size-3" />}>
          {actions.map((c) => (
            <CommandRow
              key={c.slug}
              command={c}
              disabled={!canOperate}
              onPick={onPick}
            />
          ))}
        </Section>
      )}

      {phrases.length > 0 && (
        <Section title="Frasi per il Supervisor" icon={<Type className="size-3" />}>
          {phrases.map((c) => (
            <CommandRow key={c.slug} command={c} onPick={onPick} />
          ))}
        </Section>
      )}
    </div>
  );
}

function Section({
  title,
  icon,
  children,
}: {
  title: string;
  icon: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div className="mb-1">
      <p className="flex items-center gap-1.5 px-2 py-1 font-mono text-[0.58rem] tracking-widest text-muted-foreground uppercase">
        {icon}
        {title}
      </p>
      <ul className="space-y-1">{children}</ul>
    </div>
  );
}

function CommandRow({
  command,
  onPick,
  disabled,
}: {
  command: ChatCommand;
  onPick: (command: ChatCommand) => void;
  disabled?: boolean;
}) {
  return (
    <li>
      <button
        type="button"
        disabled={disabled}
        onClick={() => onPick(command)}
        className={cn(
          "w-full rounded-lg border border-transparent px-2.5 py-2 text-left transition hover:border-border hover:bg-muted/50",
          disabled && "cursor-not-allowed opacity-50",
        )}
      >
        <span className="flex items-center gap-2">
          <span className="font-mono text-[0.68rem] text-accent">/{command.slug}</span>
          <span className="truncate text-sm font-medium">{command.label}</span>
          {command.kind === "action" && (
            <Play className="ml-auto size-3 shrink-0 text-muted-foreground" />
          )}
        </span>
        <span className="mt-0.5 block text-xs leading-snug text-muted-foreground">
          {command.description}
        </span>
      </button>
    </li>
  );
}
