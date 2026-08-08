# VIS•ION Platform Architecture v1

**VIS Intelligent Operations Network — Livello piattaforma / sistema operativo aziendale**

| Campo | Valore |
|-------|--------|
| Documento | `VISION_PLATFORM_ARCHITECTURE_v1.md` |
| Platform version | `1.0.0` |
| Baseline ufficiale correlata | `docs/VISION_API_CONTRACT_v1.md` (**non modificare**) |
| Stato | DESIGN / PREDISPOSIZIONE |
| Codice operativo | **NON modificato** in questa consegna |
| Ambito | Plugin · Skills · Capabilities · Services · Health · Supervisor |

> **Posizione nella gerarchia normativa**  
> 1. `VISION_API_CONTRACT_v1.md` = Costituzione (wire contract Core ↔ Agent ↔ PWA ↔ Backend ↔ Moduli)  
> 2. **Questo documento** = Architettura di piattaforma (come i moduli si scoprono, dichiarano capacità, condividono servizi)  
> 3. Implementazione futura = codice che deve rispettare entrambi

---

## Indice

1. [Visione: da programmi a OS aziendale](#1-visione-da-programmi-a-os-aziendale)
2. [Diagramma completo](#2-diagramma-completo-della-nuova-architettura)
3. [VisionPluginManager](#3-visionpluginmanager)
4. [VisionCapabilityRegistry](#4-visioncapabilityregistry)
5. [VisionSkillRegistry](#5-visionskillregistry)
6. [VisionServiceRegistry](#6-visionserviceregistry)
7. [VisionHealthRegistry](#7-visionhealthregistry)
8. [Supervisor indipendente](#8-supervisor-indipendente-dai-moduli)
9. [Futura AI / LLM](#9-futura-ai--llm-advisory-only)
10. [Struttura cartelle proposta](#10-struttura-cartelle-proposta)
11. [Skill Manifest](#11-skill-manifest)
12. [Flussi principali](#12-flussi-principali)
13. [Moduli e Skills previsti](#13-moduli-e-skills-previsti)
14. [Piano di migrazione](#14-piano-di-migrazione-dal-sistema-attuale)
15. [Best practice](#15-best-practice)
16. [Impatto e rischi](#16-valutazione-impatto-delle-modifiche)
17. [Consegna sintetica](#17-consegna-sintetica)

---

## 1. Visione: da programmi a OS aziendale

### 1.1 Obiettivo

VIS•ION **non** deve restare un insieme di programmi affiancati.  
Deve diventare un **sistema operativo aziendale**:

| Concetto OS | Equivalente VIS•ION |
|-------------|---------------------|
| Kernel | VisionCore |
| Process / App | Module / Plugin |
| Capability / ABI | Capability Registry |
| Service (print, net…) | Service Registry |
| Device drivers health | Health Registry |
| Soft skills / apps catalog | Skill Registry |
| Package manager | Plugin Manager |
| Shell / orchestration UI | Supervisor (+ futura PWA) |

### 1.2 Principi

1. Il **Core non conosce** la logica interna dei moduli.
2. Ogni modulo **si registra autonomamente** (manifest + register).
3. Aggiungere un modulo **non richiede** modificare il Core.
4. Il **Supervisor** conosce solo Skills, Health, Jobs, Events, Commands.
5. I servizi condivisi sono **singleton** via Service Registry (niente istanze duplicate).
6. Tutto resta conforme a `VISION_API_CONTRACT_v1.md`.

### 1.3 Cosa si predispone ora / cosa non si fa

| Ora (design) | Non ora |
|--------------|---------|
| Registri, interfacce, manifest, flussi | Logica operativa nuova |
| Documentazione piattaforma | Modifiche eniSpace / coin_transport |
| Esempi `skill.json` | Modifiche Remote Agent / PWA |
| Piano migrazione | Implementazione completa Plugin Manager |

---

## 2. Diagramma completo della nuova architettura

```
┌──────────────────────────────────────────────────────────────────────────┐
│                         VIS•ION Mobile (PWA)                             │
└─────────────────────────────────┬────────────────────────────────────────┘
                                  │ Contract v1 (commands/events/jobs)
                                  ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                      Backend (Supabase / futuro)                         │
└─────────────────────────────────┬────────────────────────────────────────┘
                                  │ outbound only
                                  ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                         Remote Agent                                     │
└─────────────────────────────────┬────────────────────────────────────────┘
                                  │
                                  ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                           VISION CORE                                    │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────┐  ┌────────────────┐ │
│  │ EventBus    │  │ JobManager   │  │ MailRouter │  │ Notification   │ │
│  └─────────────┘  └──────────────┘  └────────────┘  └────────────────┘ │
│                                                                          │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │                 PLATFORM LAYER (nuovo — design)                    │ │
│  │  PluginManager │ CapabilityRegistry │ SkillRegistry                │ │
│  │  ServiceRegistry │ HealthRegistry                                  │ │
│  └────────────────────────────────────────────────────────────────────┘ │
│                                                                          │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │ SUPERVISOR (indipendente)                                          │ │
│  │  vede: Skills · Health · Jobs · Events · Commands                  │ │
│  │  NON vede: logica interna moduli                                   │ │
│  │  futuro: LLM advisory (consulta/propone — MAI esegue)              │ │
│  └────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────┬────────────────────────────────────────┘
                                  │ load / register / health
                                  ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                        VisionPluginManager                               │
│         discover → load → register → start/stop → health → unload        │
└───┬──────┬──────┬──────┬──────┬──────┬──────┬──────┬──────┬─────────────┘
    │      │      │      │      │      │      │      │      │
    ▼      ▼      ▼      ▼      ▼      ▼      ▼      ▼      ▼
 eniSpace Coin  Protocollo HR EasyPlan Videosorv. GPS Magazzino …
          Monete
```

### 2.1 UML ASCII — relazioni registri

```
┌──────────────────┐       registers        ┌──────────────────────┐
│ VisionModule /   │ ──────────────────────►│ CapabilityRegistry   │
│ Plugin           │                        └──────────────────────┘
└────────┬─────────┘
         │ declares skills
         ▼
┌──────────────────┐                        ┌──────────────────────┐
│ Skill Manifest   │ ──────────────────────►│ SkillRegistry        │
└──────────────────┘                        └──────────────────────┘
         │
         │ uses services (by name)
         ▼
┌──────────────────┐   resolve singleton    ┌──────────────────────┐
│ Module runtime   │ ◄─────────────────────│ ServiceRegistry      │
└────────┬─────────┘                        └──────────────────────┘
         │ publishes health
         ▼
┌──────────────────┐                        ┌──────────────────────┐
│ Module           │ ──────────────────────►│ HealthRegistry       │
└──────────────────┘                        └──────────┬───────────┘
                                                       │
                                                       ▼
                                            ┌──────────────────────┐
                                            │ Supervisor           │
                                            └──────────────────────┘

┌──────────────────┐   owns lifecycle of    ┌──────────────────────┐
│ PluginManager    │ ──────────────────────►│ all of the above     │
└──────────────────┘                        └──────────────────────┘
```

---

## 3. VisionPluginManager

### 3.1 Ruolo

**Unico** responsabile del ciclo di vita dei plugin/moduli.

| Responsabilità | Descrizione |
|----------------|-------------|
| Ricerca | Scansione cartelle `plugins/` / `modules/` + manifest |
| Caricamento | Import dinamico / factory senza hard-code Core |
| Registrazione | Capability + Skill + Health |
| Avvio / Stop | Ordine rispettando dependencies |
| Health | Aggregazione verso HealthRegistry |
| Versione / compatibilità | Check `required_core_version` |
| Disinstallazione futura | Unload sicuro (design; non implementato ora) |

### 3.2 Interfaccia proposta (design)

```
VisionPluginManager
├── discover(paths) -> list[PluginDescriptor]
├── load(plugin_id) -> PluginHandle
├── register(handle) -> None
├── start(plugin_id) -> None
├── stop(plugin_id) -> None
├── unload(plugin_id) -> None          # futuro
├── list_plugins() -> list[PluginInfo]
├── get_plugin(plugin_id) -> PluginInfo | None
├── check_compatibility(manifest) -> CompatResult
└── restart(plugin_id) -> None         # stop+start isolato
```

### 3.3 PluginDescriptor (minimo)

```json
{
  "plugin_id": "enispace",
  "manifest_path": "app/modules/enispace/skill.json",
  "entry_point": "app.modules.enispace.module:EniSpaceModule",
  "discovered_at": "2026-08-08T10:00:00+02:00"
}
```

### 3.4 Regole

- Il Core chiama **solo** PluginManager per conoscere i moduli.
- Nessun `if module_id == "enispace"` nel Core.
- Fallimento load di un plugin → `ERROR` su quel plugin; **altri restano attivi**.
- Compatibilità: se `required_core_version` non soddisfatta → non start, status `DISABLED` + motivo.

### 3.5 Relazione con ModuleManager attuale

| Oggi | Domani |
|------|--------|
| `ModuleManager` (registrazione manuale in bootstrap) | Diventa **backend interno** o viene assorbito da PluginManager |
| `create_vision_core()` registra a mano eniSpace + coin_transport | PluginManager scopre manifest e registra |

Migrazione: **wrapper** — PluginManager usa ancora ModuleManager sotto, poi lo sostituisce senza cambiare contract v1.

---

## 4. VisionCapabilityRegistry

### 4.1 Ruolo

Registro centrale di **cosa sa fare** ogni modulo.  
Il Core e il Dispatcher usano questo registro per instradare comandi e validare feature.

### 4.2 Dichiarazione all’avvio (obbligatoria)

Ogni modulo, dopo `initialize` / al `start`, dichiara:

| Campo | Tipo | Note |
|-------|------|------|
| `module_id` | string | Stabile |
| `display_name` | string | UI |
| `version` | string | SemVer |
| `status` | enum | Allineato Health |
| `commands_supported` | string[] | Whitelist locale modulo |
| `events_supported` | string[] | Eventi che può emettere |
| `required_permissions` | string[] | Permessi richiesti |
| `dependencies` | string[] | Altri `module_id` / `service_id` |
| `health` | object | Snapshot iniziale |
| `metadata` | object | Extra non sensibili |

### 4.3 Interfaccia proposta

```
VisionCapabilityRegistry
├── declare(capability: ModuleCapability) -> None
├── revoke(module_id) -> None
├── get(module_id) -> ModuleCapability | None
├── list() -> list[ModuleCapability]
├── find_by_command(command_type) -> list[module_id]
├── find_by_event(event_type) -> list[module_id]
└── supports(module_id, command_type) -> bool
```

### 4.4 Esempio JSON capability

```json
{
  "module_id": "enispace",
  "display_name": "eniSpace Automation",
  "version": "1.0.0",
  "status": "ONLINE",
  "commands_supported": ["CHECK_ENISPACE_MAIL", "RETRY_JOB", "PAUSE_MODULE", "RESUME_MODULE"],
  "events_supported": ["MAIL_RECEIVED", "JOB_COMPLETED", "PRINT_FAILED", "NEEDS_ATTENTION"],
  "required_permissions": ["mail_watch", "enispace_login", "print_queue"],
  "dependencies": ["service:mail", "service:print", "service:logger"],
  "health": { "ok": true, "status": "ONLINE" },
  "metadata": { "category": "automation", "site_scoped": true }
}
```

### 4.5 Uso da Command Dispatcher

```
Command arriva
    │
    ▼
CapabilityRegistry.find_by_command(type)
    │
    ├── 0 match → REJECTED / NOT_SUPPORTED
    ├── 1 match → dispatch a quel module_id
    └── N match → policy (explicit module_id in command, else REJECTED ambigua)
```

---

## 5. VisionSkillRegistry

### 5.1 Concetto Skill

Una **Skill** è una capacità operativa di business (prodotto), non necessariamente 1:1 con un file Python.

| Skill (esempi) | Possibile provider modulo |
|----------------|---------------------------|
| eniSpace | `enispace` |
| Trasporto Monete | `coin_transport` |
| Protocollo | `protocollo` |
| Contestazioni / Elogi | `contestazioni` |
| EasyPlan | `easyplan` |
| Trasporto Valori | `valori` |
| Videosorveglianza | `video` |
| PEC | `service:pec` o modulo dedicato |
| OCR / AI Vision / Speech | servizi AI + skill che li espongono |
| Report PDF | `service:pdf` + skill reportistica |
| Mail | `service:mail` |
| Firma Digitale | `service:signature` |

Un modulo può esporre **una o più** Skills.  
Una Skill può dipendere da **servizi** condivisi.

### 5.2 Ciclo vita Skill

```
DISCOVERED (manifest)
    │
    ▼
REGISTERED
    │
    ├── ENABLED  ◄──► DISABLED
    │
    ├── UPDATED (nuova version)
    └── DEPRECATED / REMOVED (futuro)
```

### 5.3 Interfaccia proposta

```
VisionSkillRegistry
├── register(skill: SkillDescriptor) -> None
├── unregister(skill_id) -> None
├── enable(skill_id) -> None
├── disable(skill_id) -> None
├── update(skill_id, descriptor) -> None
├── get(skill_id) -> SkillDescriptor | None
├── list(filter?) -> list[SkillDescriptor]
├── list_enabled() -> list[SkillDescriptor]
└── resolve_provider(skill_id) -> module_id | service_id
```

### 5.4 Perché Skills ≠ Modules

| Module | Skill |
|--------|-------|
| Unità di deploy / codice | Unità di prodotto / UX |
| Ha processo start/stop | Può essere solo “capacità dichiarata” |
| Può fallire in isolamento | Può essere disabilitata senza unload codice |
| Esempio: `enispace` | Esempio: skill `enispace.mail_automation` |

Il Supervisor parla di **Skills** all’utente; il PluginManager parla di **Modules** al runtime.

---

## 6. VisionServiceRegistry

### 6.1 Ruolo

Servizi condivisi **singleton** richiesti dai moduli tramite Core — mai istanze duplicate.

### 6.2 Catalogo servizi previsti

| service_id | Responsabilità |
|------------|----------------|
| `logger` | Logging globale / per modulo |
| `notification` | NotificationService |
| `storage` | Path, file storage sicuro |
| `mail` | IMAP/SMTP astratto |
| `ai` | Client LLM advisory (futuro) |
| `ocr` | OCR |
| `pdf` | Generazione / preview PDF |
| `print` | Coda stampa |
| `configuration` | Config per namespace |
| `security` | Keyring / secret access scoped |
| `event_bus` | Pubblicazione eventi (solo via Core) |
| `jobs` | JobManager facade |

### 6.3 Interfaccia proposta

```
VisionServiceRegistry
├── register(service_id, factory | instance, *, singleton=True) -> None
├── get(service_id) -> Service
├── require(service_id) -> Service          # raise se assente
├── has(service_id) -> bool
├── list() -> list[ServiceInfo]
└── unregister(service_id) -> None         # raro; solo shutdown
```

### 6.4 Regola DI

```
Modulo.initialize(context):
    mail = context.services.require("mail")
    log  = context.services.require("logger")
    # MAI: MailService() locale duplicato
```

### 6.5 Diagramma

```
┌────────────┐   require("print")   ┌──────────────────┐
│ Module A   │ ────────────────────►│ ServiceRegistry  │──► PrintService (1)
└────────────┘                      └────────┬─────────┘
┌────────────┐   require("print")            │
│ Module B   │ ──────────────────────────────┘
└────────────┘         stessa istanza
```

---

## 7. VisionHealthRegistry

### 7.1 Stati standard

| Status | Significato |
|--------|-------------|
| `ONLINE` | Operativo |
| `OFFLINE` | Non disponibile |
| `DEGRADED` | Funziona a capacità ridotta |
| `ERROR` | Guasto |
| `DISABLED` | Spento volontariamente / incompatibile |
| `STARTING` | In avvio |
| `STOPPING` | In arresto |

Allineati concettualmente al contract v1; estensione `STARTING`/`STOPPING` per UX Supervisor.

### 7.2 Interfaccia proposta

```
VisionHealthRegistry
├── report(module_id | skill_id | service_id, health: HealthSnapshot) -> None
├── get(target_id) -> HealthSnapshot | None
├── list() -> list[HealthSnapshot]
├── summary() -> PlatformHealth
└── subscribe(callback) -> None            # per Supervisor / UI
```

### 7.3 HealthSnapshot

```json
{
  "target_type": "module",
  "target_id": "enispace",
  "status": "ONLINE",
  "ok": true,
  "message": "ready",
  "checked_at": "2026-08-08T10:30:00+02:00",
  "metrics": {
    "pending_jobs": 2
  }
}
```

### 7.4 PlatformHealth (aggregato)

```
ONLINE     = tutti i moduli required ONLINE
DEGRADED   = almeno un required DEGRADED o non-critical ERROR
ERROR      = required module in ERROR
DISABLED   = piattaforma in manutenzione / remote off non confondere
```

Il Remote Agent heartbeat continuerà a esportare uno snapshot compatibile contract v1 (`modules[]`).

---

## 8. Supervisor indipendente dai moduli

### 8.1 Cosa conosce

```
Supervisor
├── Skills          (SkillRegistry)
├── Health          (HealthRegistry)
├── Jobs            (JobManager / contract Job)
├── Events          (EventBus)
└── Commands        (stato comandi / Capability per routing UI)
```

### 8.2 Cosa NON conosce

- Selettori eniSpace
- Formato PEC
- Schema HR
- Dettaglio OCR interno
- Credenziali moduli

### 8.3 Beneficio

Nuovi moduli compaiono automaticamente nella dashboard Supervisor **se** dichiarano Skill + Health — senza patch al Supervisor.

### 8.4 Mapping avatar (invariato rispetto contract)

Fonte: Events + Health + Jobs — non if-per-modulo.

---

## 9. Futura AI / LLM (advisory only)

### 9.1 Ruolo previsto

```
LLM Advisor
├── consultare HealthRegistry / Jobs / Events (read-only views)
├── proporre azioni (suggerimenti di command_type)
├── generare spiegazioni per NEEDS_ATTENTION
└── MAI: eseguire comandi, codice, shell, eval
```

### 9.2 Flusso sicuro

```
Event NEEDS_ATTENTION
        │
        ▼
Supervisor chiede spiegazione a service:ai
        │
        ▼
LLM riceve: job summary + ultimi eventi (redatti)
        │
        ▼
Output: testo + optional suggested_commands[]
        │
        ▼
Umano / policy approva → solo allora Command reale
```

### 9.3 Garanzie

| Consentito | Vietato |
|------------|---------|
| Read model filtrato | Write diretto a moduli |
| Proposte | Esecuzione autonoma |
| Spiegazioni | Accesso secret |
| Classificazione assistita | Bypass approval |

Il service `ai` è registrato nel ServiceRegistry; i moduli **non** embeddano client LLM proprietari se evitabile.

---

## 10. Struttura cartelle proposta

Target evolutivo (migrazione graduale — **non applicare ora in blocco**):

```
vis-ion/
├── docs/
│   ├── VISION_API_CONTRACT_v1.md              # baseline ufficiale (LOCKED)
│   ├── VISION_PLATFORM_ARCHITECTURE_v1.md     # questo documento
│   └── platform/
│       └── examples/
│           ├── skill.enispace.example.json
│           └── skill.coin_transport.example.json
│
├── app/
│   ├── core/                  # VisionCore, EventBus, Jobs (esistente)
│   ├── platform/              # FUTURO — registri piattaforma
│   │   ├── __init__.py
│   │   ├── plugin_manager.py
│   │   ├── capability_registry.py
│   │   ├── skill_registry.py
│   │   ├── service_registry.py
│   │   ├── health_registry.py
│   │   └── interfaces.py      # Protocol / ABC
│   │
│   ├── modules/               # oppure plugins/ (alias)
│   │   ├── enispace/
│   │   │   ├── skill.json     # manifest
│   │   │   ├── module.py
│   │   │   └── ...
│   │   └── coin_transport/
│   │       ├── skill.json
│   │       └── ...
│   │
│   ├── services/              # shared service implementations
│   ├── remote/                # Remote Agent (invariato ora)
│   └── assistant/             # Supervisor / avatar
│
├── config/
│   ├── enispace/
│   ├── coin_transport/
│   └── platform/
│       └── plugins_enabled.json   # feature flags skills
│
└── main.py
```

> In questa consegna: **solo** `docs/` + esempi manifest. Nessuna cartella `app/platform/` operativa creata per non toccare il runtime.

---

## 11. Skill Manifest

### 11.1 Formato

Supportati in design: `skill.json` (preferito iniziale) o `skill.yaml`.

### 11.2 Schema campi

| Campo | Tipo | Obbligatorio | Descrizione |
|-------|------|--------------|-------------|
| `id` | string | sì | Skill id (`enispace.automation`) |
| `name` | string | sì | Display name |
| `description` | string | sì | |
| `version` | string | sì | SemVer skill |
| `author` | string | no | |
| `required_core_version` | string | sì | Es. `>=2.0.0-vision` |
| `module_id` | string | sì | Provider module |
| `commands` | string[] | sì | |
| `events` | string[] | sì | |
| `permissions` | string[] | no | |
| `dependencies` | string[] | no | `module:` / `service:` / `skill:` |
| `settings` | object | no | Schema settings UI |
| `icon` | string | no | Path asset |
| `category` | string | no | automation, logistics, hr, ai… |
| `visibility` | enum | no | `public` \| `internal` \| `hidden` |

### 11.3 Esempio completo

Vedere file:

- `docs/platform/examples/skill.enispace.example.json`
- `docs/platform/examples/skill.coin_transport.example.json`

Estratto:

```json
{
  "id": "enispace.automation",
  "name": "eniSpace Automation",
  "description": "Mail ENI/MdA, download documenti, stampa",
  "version": "1.0.0",
  "author": "VIS",
  "required_core_version": ">=2.0.0-vision",
  "module_id": "enispace",
  "commands": ["CHECK_ENISPACE_MAIL", "RETRY_JOB", "PAUSE_MODULE", "RESUME_MODULE"],
  "events": ["MAIL_RECEIVED", "JOB_COMPLETED", "PRINT_FAILED", "NEEDS_ATTENTION"],
  "permissions": ["mail_watch", "enispace_login", "print_queue"],
  "dependencies": ["service:mail", "service:print", "service:logger"],
  "settings": {
    "jarvis_interval_seconds": { "type": "integer", "default": 60 }
  },
  "icon": "assets/skills/enispace.png",
  "category": "automation",
  "visibility": "public"
}
```

---

## 12. Flussi principali

### 12.1 Boot piattaforma (target)

```
main
 │
 ▼
VisionCore.start()
 │
 ▼
ServiceRegistry.bootstrap(builtins: logger, jobs, event_bus, ...)
 │
 ▼
PluginManager.discover()
 │
 ├── load manifest skill.json
 ├── check required_core_version
 ├── instantiate module
 ├── module.initialize(context)
 ├── CapabilityRegistry.declare(...)
 ├── SkillRegistry.register(...)
 ├── HealthRegistry.report(STARTING → ONLINE|ERROR)
 └── module.start()
 │
 ▼
Supervisor.bind(registries)   # no knowledge of module internals
 │
 ▼
RemoteAgent.start() if kill switch ON
```

### 12.2 Aggiunta nuovo modulo (senza toccare Core)

```
1. Creare app/modules/<id>/
2. Aggiungere skill.json
3. Implementare VisionModule
4. (Opz.) config/<id>/
5. Abilitare in plugins_enabled.json
6. Restart / hot-load futuro
→ Capability + Skill + Health compaiono da soli
→ PWA vede nuovi command_type solo se pubblicati nel catalogo backend (additive)
```

### 12.3 Disable skill a caldo

```
Admin/PWA → policy disable skill_id
        │
        ▼
SkillRegistry.disable(skill_id)
        │
        ▼
Capability comandi associati → non dispatchabili
Module può restare loaded ma non espone skill
Health: skill DISABLED (module può restare ONLINE)
```

---

## 13. Moduli e Skills previsti

| Skill / Area | module_id suggerito | Note |
|--------------|---------------------|------|
| eniSpace | `enispace` | Esistente |
| Trasporto Monete | `coin_transport` | Scheletro esistente |
| VIS Protocollo | `protocollo` | Future |
| HR | `hr` | Future |
| EasyPlan | `easyplan` | Future |
| Videosorveglianza | `video` | Future |
| GPS / Automezzi | `fleet` | Future |
| Magazzino | `warehouse` | Future |
| Personale | `personnel` | Future (o sotto HR) |
| Contabilità | `accounting` | Future |
| PEC | `pec` o service | Shared service + skills |
| Firma Digitale | `signature` | Service |
| Reportistica | `reporting` | + service:pdf |
| AI OCR | skill + `service:ocr` | |
| AI Vision | skill + `service:ai` | |
| AI Assistant | Supervisor + `service:ai` | Advisory only |
| Contestazioni / Elogi | `contestazioni` | Future |
| Trasporto Valori | `valori` | Future |
| Mail | `service:mail` | Shared |
| Speech | `service:speech` | Future |

---

## 14. Piano di migrazione dal sistema attuale

### Fase A — Documentazione (questa consegna) ✅

- Contract v1 locked
- Platform architecture v1
- Esempi manifest

### Fase B — Registri in-process (senza cambiare comportamento)

1. Introdurre `app/platform/` con implementazioni **no-op / in-memory**
2. Wrapper: bootstrap attuale continua a registrare eniSpace/coin_transport **manualmente**, ma scrive anche nei nuovi registry
3. Nessun cambio Dispatcher/Agent

### Fase C — Manifest sui moduli esistenti

1. Aggiungere `skill.json` a eniSpace e coin_transport
2. PluginManager.discover legge manifest ma entry_point resta quello noto
3. Test regressione eniSpace invariati

### Fase D — DI servizi

1. ServiceRegistry registra logger, print, mail esistenti
2. Moduli ricevono services da context (refactor graduale)
3. Eliminare costruzioni duplicate dove sicure

### Fase E — Supervisor su registry

1. UI/Supervisor legge Skills + Health invece di liste hard-coded
2. Avatar resta event-driven (contract)

### Fase F — Discover dinamico

1. Nuovi moduli solo con cartella + manifest
2. Rimuovere registrazioni hard-coded dal bootstrap
3. Feature flag `plugins_enabled.json`

### Fase G — LLM advisory (opzionale)

1. `service:ai` read-only
2. Nessuna auto-esecuzione

**Regola migrazione:** ogni fase deve lasciare eniSpace funzionante come oggi; Remote Agent e contract v1 immutati nella semantica wire.

---

## 15. Best practice

1. **Core = kernel** — zero dominio.
2. **PluginManager = unico loader**.
3. **CapabilityRegistry = ABI comandi/eventi**.
4. **SkillRegistry = catalogo prodotto**.
5. **ServiceRegistry = singleton condivisi**.
6. **HealthRegistry = osservabilità**.
7. **Supervisor = vista astratta**.
8. **Manifest obbligatorio** per ogni plugin.
9. **Fail isolation** — errore plugin ≠ crash piattaforma.
10. **Conformità** sempre a `VISION_API_CONTRACT_v1.md`.

---

## 16. Valutazione impatto delle modifiche

### 16.1 Impatto di questa consegna (design only)

| Area | Impatto |
|------|---------|
| Runtime / eniSpace / Agent / PWA | **Nessuno** |
| Contract v1 | **Nessuno** (non modificato) |
| Legacy utility | **Nessuno** |
| Debito documentale | Positivo (roadmap chiara) |

### 16.2 Impatto implementazione futura (stima)

| Fase | Rischio | Mitigazione |
|------|---------|-------------|
| B Registri wrapper | Basso | Dual-write, feature flag |
| C Manifest | Basso | File additivi |
| D DI servizi | Medio | Refactor incrementale per servizio |
| E Supervisor registry | Medio-UI | Fallback alle liste attuali |
| F Discover dinamico | Medio-Alto | Gate test regressione eniSpace |
| G LLM | Basso se advisory-only | Deny-by-default execution |

### 16.3 Beneficio atteso

- Nuovi moduli senza patch Core
- Supervisor stabile nel tempo
- Skills abilitabili per sito (Taranto, Bari, …)
- Base solida per OS aziendale VIS•ION

### 16.4 Non-obiettivi di questa fase

- Hot-reload produzione
- Marketplace plugin pubblico
- Esecuzione autonoma AI
- Modifica schema Supabase

---

## 17. Consegna sintetica

| # | Deliverable | Dove |
|---|-------------|------|
| 1 | Diagramma architettura completa | §2 |
| 2 | Plugin Manager | §3 |
| 3 | Capability Registry | §4 |
| 4 | Skill Registry | §5 |
| 5 | Service Registry | §6 |
| 6 | Health Registry | §7 |
| 7 | Struttura cartelle proposta | §10 |
| 8 | Esempio Skill Manifest | §11 + `docs/platform/examples/` |
| 9 | Piano migrazione | §14 |
| 10 | Valutazione impatto | §16 |

### Verdetto

L’architettura a **Plugin + Skills + Capabilities + Services + Health**, con Supervisor cieco rispetto al dominio, è il livello corretto per trasformare VIS•ION in **piattaforma / OS aziendale estensibile**, restando fedele al contract v1 e senza compromettere la stabilità attuale finché la migrazione resta fasata.

---

*Fine — VIS•ION Platform Architecture v1.0.0*  
*Nessuna modifica a codice operativo, Remote Agent, moduli, PWA o `VISION_API_CONTRACT_v1.md`.*
