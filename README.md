# VIS | eniSpace Utility

Utility Windows **autonoma** per l’automazione del portale **eniSpace**.

Consente di inserire un numero contratto, accedere al portale con credenziali aziendali autorizzate, individuare gli allegati e scaricarli in una cartella locale dedicata.

> **Stato attuale:** Fasi 1–3 operative (GUI, SQLite, credenziali, Playwright, test accesso, registrazione navigazione).  
> La ricerca reale contratto → allegati → download sarà collegata dopo la **mappatura dei selettori** sul portale (Fasi 4–6).  
> **Non** dichiarare il flusso end-to-end completato finché non verificato sul portale reale.

---

## Requisiti

- Windows 10/11
- Python **3.12+**
- **Google Chrome** installato sul PC (usato da Playwright con `channel=chrome`)
- Connessione di rete verso il portale eniSpace
- Account eniSpace aziendale **autorizzato**

URL portale:

```text
https://enispace.eni.com/it_IT/home.page
```

---

## Installazione

### 1. Python

Verificare la versione:

```bat
python --version
```

Deve risultare `Python 3.12.x` o superiore.

### 2. Ambiente virtuale

Dalla cartella del progetto:

```bat
cd "C:\Users\vertigo\EniUltra\VIS eniSpace Utility"
python -m venv .venv
.venv\Scripts\activate
```

### 3. Dipendenze Python

```bat
pip install -r requirements.txt
```

### 4. Browser

Non è necessario `playwright install chromium`: l’applicazione usa **Google Chrome** già presente sul sistema (`channel=chrome`).

---

## Avvio

```bat
.venv\Scripts\activate
python app.py
```

Al primo avvio compare la **configurazione guidata**:

1. Account eniSpace (username / password)
2. Cartella download
3. Test login
4. Completamento

---

## Credenziali

- La **password non viene mai salvata in chiaro** (né in SQLite, né in JSON, né in `.env`).
- Username e password sono gestiti tramite **Windows Credential Manager** (`keyring`).
- Nel database locale può essere memorizzato al massimo lo **username**.

Impostazioni → **SALVA CREDENZIALI**.

---

## Browser nascosto (modalità hide) e DEBUG

Nelle **Impostazioni**:

| Opzione | Default | Descrizione |
|--------|---------|-------------|
| **Nascondi browser** | **ON** | Chrome resta headed (cookie/sessione OK) ma la finestra è nascosta: vedi solo l’UI dell’app |
| Modalità DEBUG | OFF | Registra URL, azione, elemento, errore |
| Timeout browser | 60000 ms | Timeout operazioni pagina |

**Primo login / MFA:** se serve autenticarsi e non vedi Chrome, disattiva temporaneamente «Nascondi browser», completa MFA, poi riattivalo. In sync automatico, se serve login l’app mostra comunque Chrome temporaneamente e scrive in ATTIVITÀ un avviso.

Durante sync/batch i PDF compaiono man mano nella scheda **CODA STAMPA** → pannello **PDF ESTRATTI** (lista + anteprima + Apri PDF / Apri cartella). La coda stampa si riempie senza chiedere conferma.

Se il login richiede **MFA / OTP / Microsoft Entra**, l’applicazione **non tenta di aggirarli**: mostra Chrome e consente il completamento manuale, poi riusa la sessione.

---

## Cartella download

Predefinita:

```text
Documenti\VIS eniSpace\<numero_contratto>\
```

Esempio:

```text
Documenti
└── VIS eniSpace
    └── 4600012345
        ├── Contratto.pdf
        ├── Capitolato.pdf
        └── DUVRI.pdf
```

Il percorso è modificabile dalle Impostazioni.

**Regole file:**

- nessun overwrite silenzioso
- confronto per nome, dimensione, data e hash **SHA-256**
- nuove versioni salvate come `Nome_rev2.pdf`, `Nome_rev3.pdf`, …
- le versioni precedenti **non** vengono eliminate

---

## Struttura progetto

```text
enispace-utility/   (VIS eniSpace Utility)
├── app.py
├── requirements.txt
├── README.md
├── build_exe.bat
├── ui/
│   ├── main_window.py
│   └── settings_window.py
├── services/
│   ├── enispace_service.py   ← logica portale (selettori da mappare)
│   ├── browser_service.py
│   ├── download_service.py
│   ├── credential_service.py
│   ├── worker.py
│   └── exceptions.py
├── database/
│   ├── db.py
│   └── models.py
├── utils/
│   ├── logger.py
│   └── paths.py
├── data/
│   ├── enispace.db
│   └── browser-profile/      ← sessione Playwright persistente
├── logs/
│   └── enispace-YYYY-MM-DD.log
└── downloads/                ← eventuale staging locale
```

---

## Test accesso eniSpace

Impostazioni → **TEST ACCESSO ENISPACE**

Esegue solo login/sessione (nessuna ricerca contratto).

---

## Modalità REGISTRA NAVIGAZIONE (acquisizione selettori)

Poiché i selettori HTML del portale **non sono inventati** nel codice, usare:

Impostazioni → **REGISTRA NAVIGAZIONE**

Cosa fa:

1. Apre **Google Chrome** visibile
2. Consente login manuale (anche MFA)
3. Mantiene il profilo/sessione in `data/browser-profile/`
4. Scrive nel log DEBUG le URL e le azioni

Apre automaticamente:

```text
https://enispace.eni.com/it_IT/home.page
```

Percorso consigliato da annotare insieme allo sviluppatore:

1. Login
2. Ricerca contratto
3. Apertura contratto
4. Pagina documenti/allegati

In alternativa, in sviluppo:

```bat
playwright codegen https://enispace.eni.com/it_IT/home.page --channel=chrome
```

I selettori vanno inseriti **solo dopo verifica** in `services/enispace_service.py` (classe `Selectors`).

---

## Logging

- Pannello **ATTIVITÀ** in basso nella GUI
- File giornaliero: `logs/enispace-YYYY-MM-DD.log`

Gli errori utente sono in italiano; **nessuno stack trace** nella GUI.

---

## Cosa funziona oggi / cosa resta da collegare

| Funzione | Stato |
|----------|--------|
| GUI ricerca / risultati / cronologia | ✅ |
| SQLite storico + impostazioni | ✅ |
| Credenziali (Credential Manager) | ✅ |
| Playwright + profilo persistente | ✅ |
| Browser visibile / DEBUG | ✅ |
| Test accesso / login manuale MFA | ✅ (URL/selettori da mappare) |
| Registra navigazione | ✅ |
| Ricerca contratto reale | ⏳ FASE 4 – selettori |
| Elenco allegati | ⏳ FASE 5 – selettori |
| Download allegati | ⏳ FASE 6 – selettori |
| Confronto nuovi documenti | ⏳ FASE 7 (logica locale già predisposta) |
| Email / VIS Protocollo | ❌ fuori scope v1 |

---

## Procedura di debug

1. Impostazioni → **Browser visibile ON**, **DEBUG ON**
2. Impostare l’URL portale (quando noto)
3. **TEST ACCESSO** oppure **REGISTRA NAVIGAZIONE**
4. Consultare `logs/enispace-*.log`
5. Annotare selettori e aggiornare `Selectors` in `enispace_service.py`

---

## Generazione EXE

Dalla cartella del progetto:

```bat
build_exe.bat
```

Genera:

```text
dist\VIS-eniSpace-Utility.exe
```

Doppio clic sull’EXE per avviare (senza aprire un terminale).

**Nota Playwright / Chrome:** l’EXE usa **Google Chrome** già installato sul PC (`channel=chrome`). Non bundle-izza Chromium e non serve `playwright install`. Database e log vengono creati accanto all’EXE (`data\`, `logs\`).

---

## Sicurezza

L’applicazione opera **solo** con l’account autorizzato fornito dall’utente.

**Non implementato / non consentito:**

- bypass CAPTCHA o MFA
- intercettazione token
- API private non documentate
- reverse engineering autenticazione
- estrazione cookie da altri browser senza consenso

---

## Estensioni future (architettura predisposta)

Moduli sostituibili per aggiungere in seguito:

- lettura automatica e-mail
- estrazione numero contratto dalla mail
- integrazione VIS Protocollo
- sincronizzazione periodica contratti
- download automatico nuovi allegati

---

## Licenza / uso

Uso interno autorizzato. Rispettare le policy aziendali Eni relative all’accesso al portale.
