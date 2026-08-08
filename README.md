# VIS•ION — VIS Intelligent Operations Network

Piattaforma centrale per le automazioni operative VIS.

> **Legacy:** il progetto originale `VIS eniSpace Utility` resta intatto come baseline stabile.
> Questo repository/cartella `vis-ion` è la copia indipendente di evoluzione.

## Avvio

```bash
python main.py
# oppure
python app.py
```

## Branding

| Chiave | Valore |
|--------|--------|
| PRODUCT_NAME | VIS•ION |
| PRODUCT_FULL_NAME | VIS Intelligent Operations Network |
| ASSISTANT_NAME | JARVIS (rinominabile in seguito) |

## Architettura

```
VIS•ION CORE
 ├── eniSpace Module      (ONLINE — logica legacy wrappata)
 ├── Trasporto Monete     (IN_DEVELOPMENT — scheletro workflow)
 └── EventBus / JobManager / MailRouter / NotificationService
```

## Isolamento dati

| Risorsa | Path |
|---------|------|
| DB app | `data/vision.db` |
| DB job globali | `data/vision_jobs.db` |
| Download | `Documents/VIS-ION/` |
| Browser profile | `data/browser-profile/` (proprio) |
| Log | `logs/vision-YYYY-MM-DD.log` |
| Config moduli | `config/enispace`, `config/mail`, `config/coin_transport` |

## Moduli

- **eniSpace Automation** — mail ENI/MdA, login, download, stampa, JARVIS Supervisor
- **Trasporto Monete** — scheletro fino a `PEC PRONTA PER APPROVAZIONE` (niente invio automatico)
