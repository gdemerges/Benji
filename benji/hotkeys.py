"""Raccourci clavier **global** macOS — celui qui marche quand Benji n'a pas le focus.

Les raccourcis existants sont des `QShortcut` posés sur l'overlay : ils ne
répondent que si Benji est au premier plan. Or pendant une réunion, le focus est
sur Teams ou Zoom, en plein écran — c'est-à-dire exactement la situation où l'on
veut couper le micro d'un geste. Un raccourci qui exige d'aller cliquer sur
Benji d'abord ne sert à rien.

**Pourquoi Carbon et pas `NSEvent.addGlobalMonitorForEventsMatchingMask_`.** Le
moniteur global Cocoa exige l'autorisation « Surveillance de la saisie » dans
Réglages Système : sans elle il ne lève aucune erreur, il ne se déclenche jamais
— le pire mode d'échec possible. `RegisterEventHotKey`, l'API historique des
raccourcis globaux, **ne demande aucune autorisation** : le système réserve la
combinaison et ne livre que celle-là, ce qui est aussi la garantie de vie privée
qu'on veut donner à l'utilisateur (Benji ne voit pas les autres frappes).

Le tout est enveloppé de garde-fous : un chargement de Carbon qui échoue, une
combinaison illisible ou déjà prise par une autre app ne font que journaliser et
rendre `register()` False. Un raccourci absent est une gêne ; une app qui ne
démarre pas est une panne.

`parse_shortcut()` est pure et porte toute la logique lisible ; le reste est du
câblage ctypes qu'aucun test ne peut exercer hors d'une session graphique.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import logging

from benji.config import IS_MACOS

log = logging.getLogger(__name__)

# Masques de modificateurs Carbon (Events.h). Ce ne sont **pas** ceux de Cocoa.
_MODIFIERS = {
    "cmd": 0x0100, "command": 0x0100, "meta": 0x0100, "⌘": 0x0100,
    "shift": 0x0200, "⇧": 0x0200,
    "alt": 0x0800, "opt": 0x0800, "option": 0x0800, "⌥": 0x0800,
    "ctrl": 0x1000, "control": 0x1000, "⌃": 0x1000,
}

# Codes de touches virtuelles (kVK_ANSI_*, Carbon/HIToolbox). Ils désignent une
# **position** sur le clavier, pas un caractère : sur un AZERTY, le code 0 est la
# touche marquée « Q ». C'est le comportement attendu d'un raccourci système.
_KEYCODES = {
    "a": 0, "s": 1, "d": 2, "f": 3, "h": 4, "g": 5, "z": 6, "x": 7, "c": 8,
    "v": 9, "b": 11, "q": 12, "w": 13, "e": 14, "r": 15, "y": 16, "t": 17,
    "1": 18, "2": 19, "3": 20, "4": 21, "6": 22, "5": 23, "9": 25, "7": 26,
    "8": 28, "0": 29, "o": 31, "u": 32, "i": 34, "p": 35, "l": 37, "j": 38,
    "k": 40, "n": 45, "m": 46,
    "return": 36, "tab": 48, "space": 49, "escape": 53, "esc": 53,
    "f1": 122, "f2": 120, "f3": 99, "f4": 118, "f5": 96, "f6": 97, "f7": 98,
    "f8": 100, "f9": 101, "f10": 109, "f11": 103, "f12": 111,
    "left": 123, "right": 124, "down": 125, "up": 126,
}


def parse_shortcut(text: str) -> tuple[int, int] | None:
    """« Ctrl+Alt+Cmd+B » → (code de touche, masque de modificateurs).

    Renvoie None si la combinaison est vide, illisible, ou **sans modificateur** :
    réserver une touche nue à l'échelle du système la retirerait de toutes les
    autres applications.
    """
    if not text:
        return None
    modifiers = 0
    key = None
    for part in (p.strip().lower() for p in text.split("+")):
        if not part:
            continue
        if part in _MODIFIERS:
            modifiers |= _MODIFIERS[part]
        elif key is None:
            key = part
        else:
            return None  # deux touches non modificatrices : combinaison absurde
    if key is None or key not in _KEYCODES or not modifiers:
        return None
    return _KEYCODES[key], modifiers


def _fourcc(code: str) -> int:
    return int.from_bytes(code.encode("ascii"), "big")


_EVENT_CLASS_KEYBOARD = _fourcc("keyb")
_EVENT_HOTKEY_PRESSED = 5
_PARAM_DIRECT_OBJECT = _fourcc("obj ")
_TYPE_HOTKEY_ID = _fourcc("hkid")
_SIGNATURE = _fourcc("bnji")


class _EventTypeSpec(ctypes.Structure):
    _fields_ = [("eventClass", ctypes.c_uint32), ("eventKind", ctypes.c_uint32)]


class _EventHotKeyID(ctypes.Structure):
    _fields_ = [("signature", ctypes.c_uint32), ("id", ctypes.c_uint32)]


_HANDLER = ctypes.CFUNCTYPE(
    ctypes.c_int32, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p
)


class GlobalHotkeys:
    """Table de raccourcis globaux, vivante tant que l'objet l'est.

    Les références Python (le trampoline ctypes, les identifiants) doivent
    survivre à `register()` : le ramasse-miettes libérerait le callback pendant
    que Carbon en tient encore l'adresse, et la première frappe planterait le
    process. C'est la raison d'être de l'instance.
    """

    def __init__(self):
        self._carbon = None
        self._handler = None      # trampoline ctypes — à garder vivant
        self._callbacks: dict[int, callable] = {}
        self._refs: list = []     # EventHotKeyRef, à garder vivants aussi
        self._next_id = 1

    # --- API ---

    def register(self, shortcut: str, callback) -> bool:
        """Réserve *shortcut* auprès du système. False = raccourci indisponible."""
        if not IS_MACOS:
            return False
        parsed = parse_shortcut(shortcut)
        if parsed is None:
            log.warning("Raccourci global illisible ou sans modificateur : %r", shortcut)
            return False
        carbon = self._load()
        if carbon is None:
            return False

        key_code, modifiers = parsed
        hotkey_id = self._next_id
        try:
            self._install_handler(carbon)
            ref = ctypes.c_void_p()
            status = carbon.RegisterEventHotKey(
                ctypes.c_uint32(key_code),
                ctypes.c_uint32(modifiers),
                _EventHotKeyID(_SIGNATURE, hotkey_id),
                carbon.GetApplicationEventTarget(),
                ctypes.c_uint32(0),
                ctypes.byref(ref),
            )
        except Exception as e:
            log.warning("Raccourci global %s indisponible (%s)", shortcut, e)
            return False
        if status != 0:
            # Le plus souvent : une autre application tient déjà la combinaison.
            log.warning("Raccourci global %s refusé par le système (statut %s)",
                        shortcut, status)
            return False

        self._callbacks[hotkey_id] = callback
        self._refs.append(ref)
        self._next_id += 1
        log.info("Raccourci global actif : %s", shortcut)
        return True

    def unregister_all(self) -> None:
        carbon = self._carbon
        if carbon is None:
            return
        for ref in self._refs:
            try:
                carbon.UnregisterEventHotKey(ref)
            except Exception:
                pass
        self._refs.clear()
        self._callbacks.clear()

    # --- câblage ---

    def _load(self):
        if self._carbon is not None:
            return self._carbon
        try:
            path = ctypes.util.find_library("Carbon")
            carbon = ctypes.CDLL(path)
            # Toute fonction appelée ici doit déclarer ses `argtypes` : sans
            # eux, ctypes passe un pointeur Python en `c_int` et rabote les 32
            # bits de poids fort. Carbon déréférence alors une demi-adresse et
            # le process meurt sur SIGSEGV, sans exception à rattraper.
            carbon.GetApplicationEventTarget.argtypes = []
            carbon.GetApplicationEventTarget.restype = ctypes.c_void_p
            carbon.RegisterEventHotKey.argtypes = [
                ctypes.c_uint32, ctypes.c_uint32, _EventHotKeyID,
                ctypes.c_void_p, ctypes.c_uint32, ctypes.POINTER(ctypes.c_void_p),
            ]
            carbon.RegisterEventHotKey.restype = ctypes.c_int32
            carbon.UnregisterEventHotKey.argtypes = [ctypes.c_void_p]
            carbon.UnregisterEventHotKey.restype = ctypes.c_int32
            carbon.InstallEventHandler.argtypes = [
                ctypes.c_void_p, _HANDLER, ctypes.c_ulong,
                ctypes.POINTER(_EventTypeSpec), ctypes.c_void_p,
                ctypes.c_void_p,
            ]
            carbon.InstallEventHandler.restype = ctypes.c_int32
            carbon.GetEventParameter.argtypes = [
                ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32,
                ctypes.c_void_p, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_void_p,
            ]
            carbon.GetEventParameter.restype = ctypes.c_int32
        except Exception as e:
            log.warning("Carbon indisponible — pas de raccourci global (%s)", e)
            return None
        self._carbon = carbon
        return carbon

    def _install_handler(self, carbon) -> None:
        """Un seul gestionnaire pour tous les raccourcis, posé au premier."""
        if self._handler is not None:
            return
        handler = _HANDLER(self._dispatch)
        spec = _EventTypeSpec(_EVENT_CLASS_KEYBOARD, _EVENT_HOTKEY_PRESSED)
        status = carbon.InstallEventHandler(
            carbon.GetApplicationEventTarget(), handler,
            1, ctypes.byref(spec), None, None,
        )
        if status != 0:
            raise OSError(f"InstallEventHandler a échoué (statut {status})")
        # Assigné seulement en cas de succès : un handler mémorisé alors que
        # Carbon ne l'a pas pris ferait croire à `register()` que le câblage est
        # posé, et le raccourci suivant ne réessaierait jamais.
        self._handler = handler

    def _dispatch(self, _next_handler, event, _user_data) -> int:
        """Appelé par Carbon sur le thread principal, à chaque frappe réservée."""
        try:
            hotkey = _EventHotKeyID()
            self._carbon.GetEventParameter(
                event, _PARAM_DIRECT_OBJECT, _TYPE_HOTKEY_ID, None,
                ctypes.c_uint32(ctypes.sizeof(hotkey)), None, ctypes.byref(hotkey),
            )
            callback = self._callbacks.get(hotkey.id)
            if callback is not None:
                callback()
        except Exception as e:
            # Une exception qui remonterait dans Carbon tuerait le process : le
            # raccourci ne doit jamais pouvoir faire tomber une réunion en cours.
            log.warning("Raccourci global : action en échec (%s)", e)
        return 0  # noErr
