import pytest

from benji.ui.window_controller import WindowController


class FakeWidget:
    def __init__(self):
        self.visible = False
    def show(self):
        self.visible = True
    def hide(self):
        self.visible = False
    def raise_(self):
        pass
    def activateWindow(self):
        pass


def test_initial_mode_window():
    win, ov = FakeWidget(), FakeWidget()
    ctl = WindowController(main_window=win, overlay=ov, initial_mode="window")
    assert ctl.mode == "window"
    assert win.visible is True
    assert ov.visible is False


def test_initial_mode_overlay():
    win, ov = FakeWidget(), FakeWidget()
    ctl = WindowController(main_window=win, overlay=ov, initial_mode="overlay")
    assert ctl.mode == "overlay"
    assert win.visible is False
    assert ov.visible is True


def test_show_overlay_hides_window():
    win, ov = FakeWidget(), FakeWidget()
    ctl = WindowController(main_window=win, overlay=ov, initial_mode="window")
    ctl.show_overlay()
    assert ctl.mode == "overlay"
    assert win.visible is False
    assert ov.visible is True


def test_show_window_hides_overlay():
    win, ov = FakeWidget(), FakeWidget()
    ctl = WindowController(main_window=win, overlay=ov, initial_mode="overlay")
    ctl.show_window()
    assert ctl.mode == "window"
    assert win.visible is True
    assert ov.visible is False


def test_toggle_alternates():
    win, ov = FakeWidget(), FakeWidget()
    ctl = WindowController(main_window=win, overlay=ov, initial_mode="window")
    ctl.toggle()
    assert ctl.mode == "overlay"
    ctl.toggle()
    assert ctl.mode == "window"
