/**
 * Catalogo comandi chat VISION.
 *
 * Due famiglie:
 * - `action`: comandi strutturati inviati all'Agent via `enqueue_supervisor_command`.
 * - `phrase`: frasi in linguaggio naturale interpretate dal Supervisor sul PC;
 *   la PWA le inserisce nel composer, non le esegue.
 */

export type ChatCommandKind = "action" | "phrase";

export type ChatCommand = {
  /** Trigger slash, senza "/". */
  slug: string;
  label: string;
  description: string;
  kind: ChatCommandKind;
  /** Solo per `action`. */
  commandType?: "WAKE_SUPERVISOR" | "DEACTIVATE_SUPERVISOR" | "GET_STATUS";
  /** Solo per `phrase`: testo precompilato nel composer. */
  template?: string;
  /** Parole chiave extra per la ricerca. */
  keywords?: string[];
};

export const CHAT_COMMAND_HELP_TRIGGERS = ["/comandi", "/help", "/?"];

export const CHAT_COMMANDS: ChatCommand[] = [
  {
    slug: "sveglia",
    label: "Sveglia Supervisor",
    description: "Invia WAKE_SUPERVISOR: avvia il Supervisor sul PC Agent.",
    kind: "action",
    commandType: "WAKE_SUPERVISOR",
    keywords: ["wake", "attiva", "risveglio"],
  },
  {
    slug: "disattiva",
    label: "Disattiva Supervisor",
    description:
      "Invia DEACTIVATE_SUPERVISOR. Azione sensibile: usa il pulsante Disattiva con conferma.",
    kind: "action",
    commandType: "DEACTIVATE_SUPERVISOR",
    keywords: ["stop", "spegni", "standby"],
  },
  {
    slug: "stato",
    label: "Stato Agent",
    description: "Invia GET_STATUS: versioni, moduli e stato corrente dell'Agent.",
    kind: "action",
    commandType: "GET_STATUS",
    keywords: ["status", "diagnostica", "versione"],
  },
  {
    slug: "parametri",
    label: "Scarica parametri cliente",
    description: "Chiede al Supervisor lo scarico parametri cliente per un periodo.",
    kind: "phrase",
    template: "Scarica parametri cliente dal 1 al 10 agosto",
    keywords: ["download", "cliente", "periodo"],
  },
  {
    slug: "scansioni",
    label: "Scarica scansioni",
    description: "Chiede al Supervisor lo scarico delle scansioni della Sala Operativa.",
    kind: "phrase",
    template: "Scarica le scansioni",
    keywords: ["sala operativa", "download"],
  },
  {
    slug: "enispace",
    label: "Attiva modulo eniSpace",
    description: "Avvia il flusso eniSpace sul PC Agent.",
    kind: "phrase",
    template: "Attiva il modulo eniSpace",
    keywords: ["modulo", "eni"],
  },
  {
    slug: "monete",
    label: "Trasporto Monete",
    description: "Avvia il flusso Trasporto Monete (può richiedere approvazione).",
    kind: "phrase",
    template: "Avvia il modulo Trasporto Monete",
    keywords: ["modulo", "pec", "approvazione"],
  },
  {
    slug: "posta",
    label: "Controlla posta",
    description: "Chiede al Supervisor di controllare la posta elettronica in arrivo.",
    kind: "phrase",
    template: "Controlla la posta elettronica",
    keywords: ["mail", "email"],
  },
  {
    slug: "riepilogo",
    label: "Riepilogo attività",
    description: "Chiede al Supervisor un riepilogo delle lavorazioni recenti.",
    kind: "phrase",
    template: "Fammi un riepilogo delle attività di oggi",
    keywords: ["report", "sintesi"],
  },
];

/** Il testo è una richiesta di help (`/comandi`, `/help`, `/?`)? */
export function isHelpCommand(text: string): boolean {
  return CHAT_COMMAND_HELP_TRIGGERS.includes(text.trim().toLowerCase());
}

/** Filtra il catalogo su una query libera o su un trigger slash. */
export function filterChatCommands(query: string): ChatCommand[] {
  const q = query.trim().toLowerCase().replace(/^\//, "");
  if (!q) return CHAT_COMMANDS;
  return CHAT_COMMANDS.filter((c) =>
    [c.slug, c.label, c.description, ...(c.keywords ?? [])]
      .join(" ")
      .toLowerCase()
      .includes(q),
  );
}
