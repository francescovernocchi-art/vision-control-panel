"""
VIS•ION — VIS Intelligent Operations Network
Entry point (compatibilità con avvio legacy `python app.py`).

Nota: `main.py` può risultare bloccato dal sistema (Accesso negato);
usare `app.py` o `run_vision.py`.
"""

from __future__ import annotations

import sys
from pathlib import Path

if not getattr(sys, "frozen", False):
    ROOT = Path(__file__).resolve().parent
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

from utils.logger import setup_logging
from utils.paths import APP_NAME, PRODUCT_FULL_NAME


def main() -> int:
    setup_logging(debug=False)
    from ui.main_window import run_app

    run_app()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print(f"\n{APP_NAME} ({PRODUCT_FULL_NAME}): interrotto.")
        raise SystemExit(130)
