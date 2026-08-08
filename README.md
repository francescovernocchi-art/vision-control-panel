# Vision Control Panel

Crea una PWA privata chiamata:

VIS•ION

VIS Intelligent Operations Network

OBIETTIVO

VIS•ION Mobile deve essere l’interfaccia remota privata del sistema VIS•ION che gira sui PC aziendali.

La PWA NON deve eseguire direttamente automazioni eniSpace, stampa, PEC o browser automation.

Deve invece:

- autenticare gli utenti;

- mostrare lo stato dei PC/Agent VIS•ION;

- mostrare i moduli disponibili;

- mostrare lavorazioni, code, errori e attività;

- ricevere notifiche;

- permettere di inviare comandi autorizzati al VIS•ION Core;

- permettere di approvare alcune operazioni sensibili;

- funzionare bene da smartphone Android, tablet e desktop;

- essere installabile come PWA.

==================================================

1. NATURA PRIVATA DELL’APP

==================================================

Questa NON è un’app pubblica.

Tutte le pagine operative devono essere protette da autenticazione.

Prima del login non devono essere visibili:

- dashboard;

- dati;

- moduli;

- lavorazioni;

- notifiche;

- utenti;

- dispositivi;

- comandi.

Prevedere una pagina login pulita con branding VIS•ION.

Usare autenticazione sicura.

Preferenza:

Supabase Auth.

Prevedere già architettura per:

- email + password;

- reset password;

- gestione sessione;

- logout;

- eventuale 2FA/MFA in fase successiva.

==================================================

2. RUOLI

==================================================

Preparare almeno questi ruoli:

ADMIN

OPERATORE

DIREZIONE

ADMIN:

- accesso completo;

- gestione utenti;

- gestione dispositivi;

- invio comandi;

- approvazioni;

- storico;

- audit.

OPERATORE:

- dashboard;

- moduli;

- lavorazioni;

- notifiche;

- comandi operativi autorizzati.

DIREZIONE:

- sola consultazione;

- dashboard;

- report;

- storico;

- nessun comando operativo pericoloso.

Implementare permessi lato UI e lato backend/database.

==================================================

3. STACK

==================================================

Usa lo stack standard Lovable:

- React

- TypeScript

- Tailwind

- shadcn/ui

- Supabase per Auth + PostgreSQL + realtime

Prepara il progetto come PWA installabile.

Aggiungi:

- manifest;

- icone PWA;

- service worker;

- modalità standalone;

- installabilità su Android.

==================================================

4. BRANDING

==================================================

Nome prodotto:

VIS•ION

Sottotitolo:

VIS Intelligent Operations Network

Descrizione:

Supervisore intelligente delle operazioni VIS

Stile visivo:

- futuristico;

- robotech;

- control room;

- professionale;

- dark theme;

- blu VIS;

- cyan neon moderato;

- vetro scuro;

- HUD leggero.

NON usare uno stile gaming eccessivo.

NON usare marchi Marvel o riferimenti Iron Man.

Lascia spazio per:

logo VIS•ION Hi-Tech

avatar robotico VIS•ION Supervisor

Gli asset definitivi verranno caricati successivamente.

==================================================

5. NAVIGAZIONE

==================================================

Sidebar / bottom navigation responsive con:

Dashboard

Supervisor

Moduli

Lavorazioni

Notifiche

Approvazioni

Dispositivi

Audit

Impostazioni

Profilo

Logout

Su mobile usare una navigazione compatta.

==================================================

6. DASHBOARD

==================================================

La Dashboard deve mostrare subito:

VIS•ION CORE

● ONLINE / OFFLINE

AGENT PRINCIPALE

● ONLINE / OFFLINE

Ultimo heartbeat

KPI:

- lavorazioni oggi;

- in elaborazione;

- in coda;

- completate;

- interventi richiesti;

- errori.

Sezione:

MODULI OPERATIVI

Card per:

eniSpace Automation

Trasporto Monete

e possibilità di aggiungere nuovi moduli in futuro.

Ogni card modulo mostra:

- stato;

- ultima attività;

- job corrente;

- eventuali errori;

- pulsante Apri modulo.

==================================================

7. SUPERVISOR

==================================================

Creare una pagina:

VIS•ION SUPERVISOR

Mostrare:

- avatar;

- stato generale;

- stato corrente;

- lavorazione attuale;

- modulo attivo;

- step corrente;

- progress;

- ultimo evento;

- eventuale richiesta di intervento.

Stati possibili:

IDLE

MAIL_RECEIVED

ANALYSIS

PROCESSING

DOWNLOAD

PRINTING

WAITING_APPROVAL

SUCCESS

ERROR

NEEDS_ATTENTION

L’avatar per ora può essere placeholder.

Prepara il componente affinché in futuro possa cambiare animazione in base allo stato.

==================================================

8. MODULO ENISPACE

==================================================

Creare la UI del modulo eniSpace.

Mostrare:

Stato modulo

Ultimo controllo mail

Ultima lavorazione

Mail rilevate

Ordine corrente

Documenti trovati

Documenti elaborati

Stato stampa

Storico recente

Comandi autorizzati:

CONTROLLA ORA LE MAIL

RIPROVA ULTIMO JOB

APRI CODA

APRI STORICO

NON simulare browser automation.

Quando l’utente invia un comando:

deve essere creato un record nella tabella commands.

==================================================

9. MODULO TRASPORTO MONETE

==================================================

Creare la UI del modulo:

TRASPORTO MONETE

Mostrare:

- stato modulo;

- nuove attività;

- mail Sala Conta;

- allegati acquisiti;

- furgoni riconosciuti;

- itinerari;

- province;

- stato documento;

- stato PEC.

Workflow visuale:

MAIL

→ ANALISI

→ ALLEGATI

→ MEZZI

→ ITINERARIO

→ DOCUMENTO

→ PEC

→ APPROVAZIONE

→ INVIO

Per ora il flusso deve fermarsi a:

PEC PRONTA PER APPROVAZIONE

Comandi:

APRI ATTIVITÀ

APRI DOCUMENTO

APRI PEC

APPROVA

RIFIUTA / RICHIEDI MODIFICA

Non effettuare realmente invii PEC.

==================================================

10. LAVORAZIONI

==================================================

Creare pagina:

LAVORAZIONI

Tabella/lista responsive con:

ID

Modulo

Titolo

Data

Stato

Progress

Durata

Operatore

Dispositivo

Stati:

PENDING

QUEUED

PROCESSING

WAITING_APPROVAL

COMPLETED

PARTIAL

NEEDS_ATTENTION

FAILED

CANCELLED

Filtri:

Modulo

Stato

Data

Ricerca

==================================================

11. DETTAGLIO JOB

==================================================

Pagina:

/jobs/:id

Mostrare:

ID job

Modulo

Sorgente

Data creazione

Data avvio

Data fine

Stato

Progress

Step corrente

Errori

Metadata

Timeline eventi

Comandi disponibili

==================================================

12. NOTIFICHE

==================================================

Creare pagina:

NOTIFICHE

Tipologie:

JOB_COMPLETED

JOB_FAILED

NEEDS_ATTENTION

WAITING_APPROVAL

MODULE_OFFLINE

DEVICE_OFFLINE

Mostrare:

- titolo;

- messaggio;

- modulo;

- data/ora;

- stato letta/non letta;

- link al job.

Prepara architettura per notifiche push PWA.

Se possibile implementa il supporto tecnico PWA per Web Push.

Se richiede configurazione esterna, prepara l’interfaccia e documenta cosa manca.

==================================================

13. APPROVAZIONI

==================================================

Creare pagina:

APPROVAZIONI

Mostrare solo job che richiedono conferma.

Esempio:

TRASPORTO MONETE

PEC pronta

Data:

08/08/2026

Province:

TA / BR / LE

Azioni:

APRI DETTAGLIO

APPROVA

RICHIEDI MODIFICA

ANNULLA

Per operazioni sensibili mostrare sempre una seconda conferma.

==================================================

14. COMANDI REMOTI

==================================================

La PWA non deve eseguire codice arbitrario.

Creare un sistema basato su whitelist.

Comandi iniziali:

GET_STATUS

CHECK_ENISPACE_MAIL

RETRY_JOB

PAUSE_MODULE

RESUME_MODULE

PREPARE_COIN_TRANSPORT

APPROVE_JOB

REJECT_JOB

Ogni comando deve avere:

command_id

command_type

module_id

target_device_id

requested_by

requested_at

status

parameters

executed_at

result

error

Stati comando:

PENDING

ACKNOWLEDGED

EXECUTING

COMPLETED

FAILED

REJECTED

==================================================

15. DISPOSITIVI

==================================================

Pagina:

DISPOSITIVI

Mostrare i PC/Agent VIS•ION.

Esempio:

VIS-TARANTO-01

● ONLINE

Ultimo heartbeat:

08:42:12

Versione:

1.0

Moduli:

eniSpace

Trasporto Monete

CPU / RAM / rete possono essere opzionali.

Stati:

ONLINE

DEGRADED

OFFLINE

DISABLED

==================================================

16. DATABASE

==================================================

Crea schema Supabase indicativo con tabelle:

profiles

roles

devices

modules

device_modules

vision_jobs

job_events

commands

notifications

approvals

audit_logs

user_devices

Pensa fin dall’inizio alla Row Level Security.

==================================================

17. RLS

==================================================

Configurare Row Level Security.

Regole:

un utente non autenticato:

nessun accesso.

DIREZIONE:

lettura delle entità autorizzate.

OPERATORE:

lettura + creazione comandi consentiti.

ADMIN:

accesso completo.

Le autorizzazioni critiche non devono dipendere esclusivamente dal frontend.

==================================================

18. AUDIT

==================================================

Ogni azione importante deve generare audit log.

Registrare:

utente

timestamp

azione

modulo

job

dispositivo

IP se disponibile

esito

metadata

Audit per:

login

logout

comando inviato

approvazione

rifiuto

modifica configurazione

gestione utente

==================================================

19. REALTIME

==================================================

Usa Supabase Realtime per aggiornare:

stato dispositivi

stato moduli

job

eventi

comandi

notifiche

approvazioni

La dashboard non deve richiedere refresh manuale.

==================================================

20. HEARTBEAT

==================================================

Preparare il modello dati per heartbeat Agent.

Ogni dispositivo deve aggiornare:

last_seen_at

status

agent_version

current_job_id

metadata

La UI considera offline un device che non invia heartbeat entro una soglia configurabile.

==================================================

21. API / INTEGRAZIONE PYTHON

==================================================

La PWA dovrà essere collegata al VIS•ION Agent Python.

NON implementare browser automation.

Prepara una chiara integrazione tramite Supabase / API.

Il Python Agent dovrà poter:

- leggere commands PENDING;

- aggiornare status;

- creare job;

- aggiungere job_events;

- aggiornare module status;

- aggiornare device heartbeat;

- creare notifications.

Prepara documentazione tecnica degli endpoint/tabelle che il Python Agent dovrà usare.

==================================================

22. SICUREZZA

==================================================

NON salvare credenziali eniSpace nella PWA.

NON salvare password PEC.

NON salvare credenziali browser automation.

Quelle rimangono sul PC VIS.

La PWA deve gestire solo:

- utenti;

- autorizzazioni;

- comandi;

- stato;

- eventi;

- notifiche;

- approvazioni.

==================================================

23. AZIONI SENSIBILI

==================================================

Azioni come:

APPROVA PEC

INVIA PEC

CANCELLA JOB

DISABILITA AGENT

devono richiedere conferma esplicita.

Per ora NON implementare INVIA PEC come azione reale.

Prepara solo il modello.

==================================================

24. MOBILE FIRST

==================================================

La PWA deve essere eccellente su Android.

Dashboard mobile:

VIS•ION

● Core Online

4 KPI compatti

Supervisor

Moduli

Attività recente

Bottom navigation.

Le card devono essere facilmente utilizzabili con una mano.

==================================================

25. INSTALLAZIONE PWA

==================================================

Preparare:

manifest.json

nome:

VIS•ION

short name:

VIS•ION

display:

standalone

theme_color coerente con UI.

Aggiungere supporto:

“Installa VIS•ION”

quando disponibile.

==================================================

26. STATO CONNESSIONE

==================================================

Mostrare chiaramente:

Cloud online/offline

Agent online/offline

Modulo online/offline

Se il telefono perde Internet:

mostrare chiaramente modalità offline.

NON consentire invio comandi senza connessione.

==================================================

27. ERRORI

==================================================

Ogni errore deve essere leggibile.

Esempio:

AGENT OFFLINE

Non è possibile inviare il comando perché VIS-TARANTO-01 non è raggiungibile.

Oppure:

COMANDO FALLITO

CHECK_ENISPACE_MAIL

Errore restituito dal dispositivo:

Login eniSpace non riuscito.

==================================================

28. PLACEHOLDER DATI

==================================================

Per la prima build usa dati demo realistici.

Esempio:

VIS-TARANTO-01

ONLINE

eniSpace

ONLINE

Trasporto Monete

ONLINE

Job:

VISION-2026-000128

Non simulare risultati impossibili.

Segnala chiaramente quando i dati sono demo.

==================================================

29. FUTURI MODULI

==================================================

L’architettura deve permettere l’aggiunta futura di:

VIS Protocollo

HR

Contestazioni ed Elogi

EasyPlan

Trasporto Valori

Gare / Manodopera

senza rifare la dashboard.

==================================================

30. OBIETTIVO UX

==================================================

In pochi secondi devo capire:

VIS•ION è online?

Il PC aziendale è online?

Ci sono lavori attivi?

Ci sono errori?

Ci sono PEC da approvare?

Qual è l’ultima attività?

Posso impartire un comando?

==================================================

31. NON FARE

==================================================

NON creare una landing page marketing.

NON creare sito pubblico.

NON usare dati aziendali reali.

NON esporre secret.

NON implementare automazioni PC nel browser.

NON inventare API esistenti.

NON collegare direttamente la PWA al PC con IP pubblico.

==================================================

32. PRIMA CONSEGNA

==================================================

Costruisci una prima versione completa con:

- autenticazione;

- dashboard;

- moduli;

- eniSpace;

- Trasporto Monete;

- lavori;

- notifiche;

- approvazioni;

- dispositivi;

- audit;

- PWA installabile;

- database Supabase;

- realtime;

- UI responsive.

Poi fornisci un report con:

1. struttura realizzata;

2. schema DB;

3. RLS;

4. pagine;

5. ruoli;

6. comandi disponibili;

7. integrazione richiesta lato Python;

8. configurazioni mancanti;

9. come installare la PWA sul telefono;

10. cosa serve per abilitare le notifiche push.

IMPORTANTE

Questa PWA sarà il TERMINALE REMOTO PRIVATO di VIS•ION.

Il motore operativo resta il programma Python VIS•ION Agent sul PC aziendale.

Non duplicare nel frontend la logica operativa del Python Agent.

This project was built with [Lovable](https://lovable.dev).

## Build with Lovable

Continue developing this project in the [Lovable editor](https://lovable.dev/projects/8ec099a1-d39e-4f80-932e-a6bbccc2782a).

- **Ship faster**: describe what you want to build and Lovable handles the code.
- **Stay in sync**: every change made in Lovable is committed straight to this repository.
- **Full ownership**: this code is yours. Push to `main` on GitHub and your changes sync back into Lovable, ready for your next prompt.

## Development

Prefer working locally? You need Node.js and npm — [install with nvm](https://github.com/nvm-sh/nvm#installing-and-updating).

```sh
git clone <this-repository-url>
cd <repository-name>
npm i
npm run dev
```
