# Avatar JARVIS — asset e sostituzione immagini

Cartella usata dall’UI (`ui/jarvis_avatar.py`). Solo presentazione: non influenza mail, download, stampa o supervisore.

## Struttura

```
assets/jarvis/
  jarvis_avatar_base.png     # frame base (512×512 consigliato)
  jarvis_idle/               # IDLE / attesa
  jarvis_mail/               # mail rilevata
  jarvis_analisi/            # analisi mail / contratto
  jarvis_accesso/            # accesso eniSpace / ricerca
  jarvis_download/
  jarvis_stampa/
  jarvis_completato/
  jarvis_errore/
  jarvis_intervento/
```

## Come sostituire le immagini (senza toccare il codice)

1. Esporta PNG (RGBA, preferibilmente **512×512** o multipli).
2. Mettili nella cartella dello stato, nominati in ordine alfabetico:
   - `frame_000.png`, `frame_001.png`, `frame_002.png`, …
3. All’avvio l’avatar carica automaticamente tutti i `.png` / `.webp` / `.jpg` della cartella.
4. Se una cartella è vuota o manca, si usa `jarvis_avatar_base.png` + overlay HUD procedurali (cerchi, radar, pulse).
5. Logo petto: `assets/vis_jarvis_logo.png` viene sovrapposto a runtime; puoi anche incorporarlo nei tuoi PNG.

## Livello animazioni (Impostazioni → JARVIS)

| UI           | Valore DB | Effetto                          |
|--------------|-----------|----------------------------------|
| Complete     | `full`    | ~20–30 FPS, HUD completo         |
| Ridotte      | `reduced` | FPS ridotti, HUD leggero         |
| Disattivate  | `off`     | Frame statico, nessun after loop |

Setting: `jarvis_avatar_level` (solo preferenza UI).

## Stati collegati

L’avatar riceve `jarvis.snapshot()["state"]` (stringhe `JarvisState`) dal refresh UI esistente; non ascolta i thread del supervisore.
