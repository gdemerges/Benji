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

**Windows et Linux (2026-09-18)**, même philosophie, deux implémentations
distinctes — les API n'ont rien de commun avec Carbon, seul le tokenizer
« Ctrl+Alt+Cmd+B » → modificateurs/touche est partagé (`_tokenize`).

- `WindowsHotkeys` — `RegisterHotKey` + interception de `WM_HOTKEY` sur la
  boucle de messages que Qt fait déjà tourner (`QAbstractNativeEventFilter`),
  pas de fil dédié à ouvrir. **Non validé sur machine réelle** — aucun poste
  Windows disponible pour ce projet ; même statut que Carbon à sa création
  (cf. le suivi « À valider au runtime » du vault).
- `LinuxHotkeys` — `XGrabKey` (Xlib, ctypes, comme Carbon : pas de nouvelle
  dépendance) sur une connexion X11 **dédiée**, pompée par un fil à part (Qt
  utilise XCB, pas Xlib — mélanger les deux sur la même connexion n'est pas
  sûr). Grab posé en quatre combinaisons (avec/sans Verr Num, Verr Maj) : X11
  inclut ces verrous dans l'état des modificateurs, les ignorer ferait rater
  le raccourci une fois sur quatre selon l'état du clavier. **Sous Wayland,
  ça échoue silencieusement** — la capture globale de touches y est interdite
  par design sans portail spécifique au compositeur, aucune solution unifiée
  n'existe ; `register()` rend False comme n'importe quel raccourci
  indisponible, sans jamais bloquer le démarrage.

`build_hotkeys()` choisit l'implémentation à la construction ; `benji/app.py`
l'appelle plutôt que d'instancier `GlobalHotkeys` (Carbon) directement.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import logging
import threading

from benji.config import IS_LINUX, IS_MACOS, IS_WINDOWS

log = logging.getLogger(__name__)

# Alias de modificateurs, communs aux trois systèmes : c'est ce que
# l'utilisateur tape ("Cmd" a un sens même sur Windows/Linux, où il vise le
# meilleur équivalent local — la touche Windows / Super). Seul l'encodage en
# code natif diffère ensuite, par système.
_MOD_ALIASES = {
    "cmd": "cmd", "command": "cmd", "meta": "cmd", "win": "cmd", "super": "cmd", "⌘": "cmd",
    "shift": "shift", "⇧": "shift",
    "alt": "alt", "opt": "alt", "option": "alt", "⌥": "alt",
    "ctrl": "ctrl", "control": "ctrl", "⌃": "ctrl",
}


def _tokenize(text: str) -> tuple[list[str], str] | None:
    """« Ctrl+Alt+Cmd+B » → (["ctrl", "alt", "cmd"], "b"), pure et partagée.

    Seule la validation générique (combinaison vide, deux touches non
    modificatrices, aucun modificateur) est commune : reconnaître la touche
    elle-même et l'encoder revient à l'appelant, chaque système ayant son
    propre jeu de codes.
    """
    if not text:
        return None
    mods: list[str] = []
    key: str | None = None
    for part in (p.strip().lower() for p in text.split("+")):
        if not part:
            continue
        if part in _MOD_ALIASES:
            mods.append(_MOD_ALIASES[part])
        elif key is None:
            key = part
        else:
            return None  # deux touches non modificatrices : combinaison absurde
    if key is None or not mods:
        return None
    return mods, key

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
    """« Ctrl+Alt+Cmd+B » → (code de touche Carbon, masque de modificateurs).

    Renvoie None si la combinaison est vide, illisible, ou **sans modificateur** :
    réserver une touche nue à l'échelle du système la retirerait de toutes les
    autres applications.
    """
    tok = _tokenize(text)
    if tok is None:
        return None
    mods, key = tok
    if key not in _KEYCODES:
        return None
    modifiers = 0
    for m in mods:
        modifiers |= _MODIFIERS[m]
    return _KEYCODES[key], modifiers


# --- Windows : RegisterHotKey (WinUser.h) ---

_WIN_MODIFIERS = {"alt": 0x0001, "ctrl": 0x0002, "shift": 0x0004, "cmd": 0x0008}  # MOD_*
# Codes de touche virtuelle (VK_*). Lettres/chiffres = leur code ASCII majuscule,
# c'est la seule coïncidence pratique de tout ce fichier.
_WIN_VK = {
    **{c: ord(c.upper()) for c in "abcdefghijklmnopqrstuvwxyz"},
    **{d: ord(d) for d in "0123456789"},
    "return": 0x0D, "tab": 0x09, "space": 0x20, "escape": 0x1B, "esc": 0x1B,
    "f1": 0x70, "f2": 0x71, "f3": 0x72, "f4": 0x73, "f5": 0x74, "f6": 0x75,
    "f7": 0x76, "f8": 0x77, "f9": 0x78, "f10": 0x79, "f11": 0x7A, "f12": 0x7B,
    "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28,
}


def parse_shortcut_windows(text: str) -> tuple[int, int] | None:
    """« Ctrl+Alt+Cmd+B » → (code VK, masque MOD_*). None si illisible."""
    tok = _tokenize(text)
    if tok is None:
        return None
    mods, key = tok
    if key not in _WIN_VK:
        return None
    modifiers = 0
    for m in mods:
        modifiers |= _WIN_MODIFIERS[m]
    return _WIN_VK[key], modifiers


# --- Linux/X11 : XGrabKey (Xlib) ---

_X11_MODIFIERS = {"shift": 1, "ctrl": 4, "alt": 8, "cmd": 64}  # Shift/Control/Mod1/Mod4
# Verrous que X11 mélange à l'état des modificateurs (Xlib ne les ignore pas
# de lui-même) : sans les inclure dans les combinaisons grabées, le raccourci
# raterait chaque fois que Verr Num ou Verr Maj est actif.
_X11_LOCK_MASKS = (0, 2, 16, 2 | 16)  # aucun, Verr Maj (Lock), Verr Num (Mod2), les deux
# Noms de touche attendus par `XStringToKeysym` — pas nos propres alias.
_X11_KEYSYMS = {
    **{c: c for c in "abcdefghijklmnopqrstuvwxyz"},
    **{d: d for d in "0123456789"},
    "return": "Return", "tab": "Tab", "space": "space",
    "escape": "Escape", "esc": "Escape",
    "f1": "F1", "f2": "F2", "f3": "F3", "f4": "F4", "f5": "F5", "f6": "F6",
    "f7": "F7", "f8": "F8", "f9": "F9", "f10": "F10", "f11": "F11", "f12": "F12",
    "left": "Left", "up": "Up", "right": "Right", "down": "Down",
}


def parse_shortcut_x11(text: str) -> tuple[str, int] | None:
    """« Ctrl+Alt+Cmd+B » → (nom de touche X11, masque Shift/Control/Mod1/Mod4).

    Le nom (pas un code) parce que la conversion en `KeyCode` dépend de la
    disposition clavier active, résolue seulement à l'enregistrement — via
    `XStringToKeysym` puis `XKeysymToKeycode`, contre un vrai `Display`.
    """
    tok = _tokenize(text)
    if tok is None:
        return None
    mods, key = tok
    if key not in _X11_KEYSYMS:
        return None
    modifiers = 0
    for m in mods:
        modifiers |= _X11_MODIFIERS[m]
    return _X11_KEYSYMS[key], modifiers


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


_WM_HOTKEY = 0x0312


class WindowsHotkeys:
    """Raccourci global Windows — `RegisterHotKey` + `WM_HOTKEY`.

    Qt fait déjà tourner la boucle de messages Windows pour ses propres
    fenêtres : `QAbstractNativeEventFilter` intercepte les messages qui y
    transitent au lieu d'ouvrir un fil dédié, comme le fait déjà chaque
    fenêtre Qt pour les siens. **Non validé sur machine réelle.**
    """

    def __init__(self):
        from PySide6.QtCore import QAbstractNativeEventFilter

        class _Filter(QAbstractNativeEventFilter):
            def __init__(self, owner):
                super().__init__()
                self._owner = owner

            def nativeEventFilter(self, _event_type, message):
                self._owner._on_native_event(message)
                return False, 0

        self._filter = _Filter(self)
        self._user32 = None
        self._callbacks: dict[int, callable] = {}
        self._next_id = 1
        self._installed = False

    def _load(self):
        if self._user32 is not None:
            return self._user32
        try:
            user32 = ctypes.windll.user32  # type: ignore[attr-defined]
            # Comme Carbon/X11 (cf. GlobalHotkeys._load, LinuxHotkeys._load) :
            # sans argtypes déclarés, ctypes peut tronquer HWND (un pointeur)
            # en c_int et faire dérailler le process sur SIGSEGV.
            user32.RegisterHotKey.argtypes = [
                ctypes.c_void_p, ctypes.c_int, ctypes.c_uint, ctypes.c_uint,
            ]
            user32.RegisterHotKey.restype = ctypes.c_int
            user32.UnregisterHotKey.argtypes = [ctypes.c_void_p, ctypes.c_int]
            user32.UnregisterHotKey.restype = ctypes.c_int
        except Exception as e:
            log.warning("user32 indisponible — pas de raccourci global (%s)", e)
            return None
        self._user32 = user32
        return user32

    def register(self, shortcut: str, callback) -> bool:
        if not IS_WINDOWS:
            return False
        parsed = parse_shortcut_windows(shortcut)
        if parsed is None:
            log.warning("Raccourci global illisible ou sans modificateur : %r", shortcut)
            return False
        user32 = self._load()
        if user32 is None:
            return False

        vk, mods = parsed
        hotkey_id = self._next_id
        # MOD_NOREPEAT (0x4000) : un seul déclenchement par appui, pas une
        # rafale tant que la touche reste enfoncée.
        if not user32.RegisterHotKey(None, hotkey_id, mods | 0x4000, vk):
            log.warning("Raccourci global %s refusé par le système", shortcut)
            return False

        if not self._installed:
            from PySide6.QtCore import QCoreApplication

            app = QCoreApplication.instance()
            if app is None:
                # Ne devrait pas arriver (app.py installe après _create_qapp),
                # mais un raccourci sans app plutôt qu'un crash au démarrage.
                user32.UnregisterHotKey(None, hotkey_id)
                log.warning("Aucun QCoreApplication actif — raccourci global impossible")
                return False
            app.installNativeEventFilter(self._filter)
            self._installed = True

        self._callbacks[hotkey_id] = callback
        self._next_id += 1
        log.info("Raccourci global actif : %s", shortcut)
        return True

    def _on_native_event(self, message) -> None:
        try:
            import ctypes.wintypes as wintypes

            msg = wintypes.MSG.from_address(int(message))
        except Exception:
            return
        if msg.message != _WM_HOTKEY:
            return
        callback = self._callbacks.get(msg.wParam)
        if callback is not None:
            try:
                callback()
            except Exception as e:
                log.warning("Raccourci global : action en échec (%s)", e)

    def unregister_all(self) -> None:
        if self._user32 is None:
            return
        for hotkey_id in self._callbacks:
            try:
                self._user32.UnregisterHotKey(None, hotkey_id)
            except Exception:
                pass
        self._callbacks.clear()


class _XKeyEvent(ctypes.Structure):
    _fields_ = [
        ("type", ctypes.c_int), ("serial", ctypes.c_ulong),
        ("send_event", ctypes.c_int), ("display", ctypes.c_void_p),
        ("window", ctypes.c_ulong), ("root", ctypes.c_ulong),
        ("subwindow", ctypes.c_ulong), ("time", ctypes.c_ulong),
        ("x", ctypes.c_int), ("y", ctypes.c_int),
        ("x_root", ctypes.c_int), ("y_root", ctypes.c_int),
        ("state", ctypes.c_uint), ("keycode", ctypes.c_uint),
        ("same_screen", ctypes.c_int),
    ]


class _XEvent(ctypes.Union):
    """`XEvent` est une union C ; `pad` réserve la taille réelle (24 longs,
    la marge que Xlib.h lui-même garantit) pour que `XNextEvent` n'écrive
    jamais hors de ce que ctypes a alloué, quel que soit le type reçu."""

    _fields_ = [("type", ctypes.c_int), ("xkey", _XKeyEvent), ("pad", ctypes.c_long * 24)]


_KEY_PRESS = 2


class LinuxHotkeys:
    """Raccourci global Linux (X11 seulement) — `XGrabKey` sur une connexion
    Xlib **dédiée**, pompée par un fil à part : Qt utilise XCB pour la sienne,
    mélanger les deux protocoles sur la même connexion n'est pas sûr.

    Grabe quatre combinaisons par raccourci (avec/sans Verr Maj, Verr Num) :
    X11 inclut ces verrous dans l'état des modificateurs de chaque événement,
    les ignorer ferait rater le raccourci selon l'état du clavier au moment
    de l'appui. **Sous Wayland, `register()` échoue silencieusement** — la
    capture globale y est interdite par design sans portail spécifique au
    compositeur. **Non validé sur machine réelle.**
    """

    def __init__(self):
        self._x11 = None
        self._display = None
        self._callbacks: dict[int, callable] = {}  # keycode|state → callback
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    def register(self, shortcut: str, callback) -> bool:
        if not IS_LINUX:
            return False
        parsed = parse_shortcut_x11(shortcut)
        if parsed is None:
            log.warning("Raccourci global illisible ou sans modificateur : %r", shortcut)
            return False
        x11 = self._load()
        if x11 is None:
            return False

        keysym_name, mods = parsed
        keysym = x11.XStringToKeysym(keysym_name.encode("ascii"))
        keycode = x11.XKeysymToKeycode(self._display, keysym)
        if keycode == 0:
            log.warning("Raccourci global %s : touche introuvable sur ce clavier", shortcut)
            return False
        root = x11.XDefaultRootWindow(self._display)
        try:
            for lock in _X11_LOCK_MASKS:
                x11.XGrabKey(
                    self._display, keycode, mods | lock, root, True, 1, 1  # GrabModeAsync
                )
        except Exception as e:
            log.warning("Raccourci global %s refusé par le système (%s)", shortcut, e)
            return False
        x11.XFlush(self._display)

        for lock in _X11_LOCK_MASKS:
            self._callbacks[(keycode, mods | lock)] = callback
        self._ensure_pump()
        log.info("Raccourci global actif : %s", shortcut)
        return True

    def _load(self):
        if self._x11 is not None:
            return self._x11
        try:
            path = ctypes.util.find_library("X11")
            x11 = ctypes.CDLL(path)
            # Comme Carbon (cf. GlobalHotkeys._load) : sans argtypes déclarés,
            # ctypes peut tronquer un pointeur 64 bits en c_int et faire
            # dérailler le process sur SIGSEGV, sans exception à rattraper.
            x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
            x11.XOpenDisplay.restype = ctypes.c_void_p
            x11.XStringToKeysym.argtypes = [ctypes.c_char_p]
            x11.XStringToKeysym.restype = ctypes.c_ulong
            x11.XKeysymToKeycode.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
            x11.XKeysymToKeycode.restype = ctypes.c_ubyte
            x11.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
            x11.XDefaultRootWindow.restype = ctypes.c_ulong
            x11.XGrabKey.argtypes = [
                ctypes.c_void_p, ctypes.c_int, ctypes.c_uint, ctypes.c_ulong,
                ctypes.c_int, ctypes.c_int, ctypes.c_int,
            ]
            x11.XGrabKey.restype = ctypes.c_int
            x11.XUngrabKey.argtypes = [
                ctypes.c_void_p, ctypes.c_int, ctypes.c_uint, ctypes.c_ulong,
            ]
            x11.XUngrabKey.restype = ctypes.c_int
            x11.XFlush.argtypes = [ctypes.c_void_p]
            x11.XFlush.restype = ctypes.c_int
            x11.XNextEvent.argtypes = [ctypes.c_void_p, ctypes.POINTER(_XEvent)]
            x11.XNextEvent.restype = ctypes.c_int
            display = x11.XOpenDisplay(None)
            if not display:
                # Pas de serveur X — Wayland pur, ou aucune session graphique.
                log.warning("Aucune connexion X11 — pas de raccourci global (Wayland ?)")
                return None
        except Exception as e:
            log.warning("Xlib indisponible — pas de raccourci global (%s)", e)
            return None
        self._x11 = x11
        self._display = display
        return x11

    def _ensure_pump(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(
            target=self._pump, daemon=True, name="X11-hotkeys"
        )
        self._thread.start()

    def _pump(self) -> None:
        event = _XEvent()
        while not self._stop.is_set():
            # Bloquant : un fil démon dédié, jamais celui de Qt — une frappe
            # réservée ne doit pas attendre le tick de la boucle applicative.
            try:
                self._x11.XNextEvent(self._display, ctypes.byref(event))
            except Exception:
                return
            if event.type != _KEY_PRESS:
                continue
            callback = self._callbacks.get((event.xkey.keycode, event.xkey.state))
            if callback is None:
                continue
            try:
                callback()
            except Exception as e:
                log.warning("Raccourci global : action en échec (%s)", e)

    def unregister_all(self) -> None:
        if self._x11 is not None and self._display is not None:
            try:
                root = self._x11.XDefaultRootWindow(self._display)
                for keycode, mods in self._callbacks:
                    self._x11.XUngrabKey(self._display, keycode, mods, root)
                self._x11.XFlush(self._display)
            except Exception:
                pass
        self._callbacks.clear()
        self._stop.set()


def build_hotkeys():
    """Choisit l'implémentation selon l'OS courant.

    macOS reste `GlobalHotkeys` (Carbon, historique) ; Windows et Linux
    utilisent les classes ci-dessus. `benji/app.py` appelle cette factory
    plutôt que d'instancier une classe en dur.
    """
    if IS_WINDOWS:
        return WindowsHotkeys()
    if IS_LINUX:
        return LinuxHotkeys()
    return GlobalHotkeys()
