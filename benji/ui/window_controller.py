"""Bascule mutuellement exclusive entre fenêtre principale et overlay."""

from __future__ import annotations

from typing import Literal

Mode = Literal["window", "overlay"]


class WindowController:
    def __init__(self, main_window, overlay, initial_mode: Mode = "window"):
        self._main = main_window
        self._overlay = overlay
        self._mode: Mode = initial_mode
        if initial_mode == "window":
            self._activate_window()
        else:
            self._activate_overlay()

    @property
    def mode(self) -> Mode:
        return self._mode

    def show_window(self) -> None:
        if self._mode == "window":
            return
        self._activate_window()

    def show_overlay(self) -> None:
        if self._mode == "overlay":
            return
        self._activate_overlay()

    def toggle(self) -> None:
        if self._mode == "window":
            self.show_overlay()
        else:
            self.show_window()

    def _activate_window(self) -> None:
        self._overlay.hide()
        self._main.show()
        self._main.raise_()
        self._main.activateWindow()
        self._mode = "window"

    def _activate_overlay(self) -> None:
        self._main.hide()
        self._overlay.show()
        self._overlay.raise_()
        self._mode = "overlay"
