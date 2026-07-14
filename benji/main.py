"""Point d'entrée Benji.

Volontairement mince : il ne fait que (1) configurer le logging, (2) poser la
politique « accessory » macOS AVANT tout import Qt, puis (3) déléguer au
composition root `BenjiApplication` (cf. benji/app.py). Garder l'ordre des deux
premières étapes — Qt verrouille la politique d'activation dès qu'il s'initialise.
"""

import logging
import platform

from benji.logging_config import setup_logging
from benji.monitoring import init_sentry

setup_logging()
init_sentry()  # no-op sans BENJI_SENTRY_DSN
log = logging.getLogger(__name__)


def _promote_to_accessory_app():
    """Convert the process to an 'accessory' app BEFORE any Qt/AppKit init.

    On macOS 13+ this is required for a window to float over another app's
    native fullscreen Space. Must run before QApplication is instantiated,
    otherwise Qt locks the activation policy to 'regular'.
    """
    if platform.system() != "Darwin":
        return
    try:
        from AppKit import NSApplication, NSApplicationActivationPolicyAccessory
        NSApplication.sharedApplication().setActivationPolicy_(
            NSApplicationActivationPolicyAccessory
        )
    except Exception as e:
        log.warning("Could not set accessory policy: %s", e)


def main():
    # Avant tout import de PyQt (fait par benji.app) : politique accessory macOS.
    _promote_to_accessory_app()

    from benji.app import BenjiApplication

    raise SystemExit(BenjiApplication().run())


if __name__ == "__main__":
    main()
