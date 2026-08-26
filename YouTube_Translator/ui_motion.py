"""Микро-анимации кнопок (слой G): hover/press + busy pulse.

Без Lottie и без CSS keyframes — только QPropertyAnimation на opacity.
Если на кнопке уже QGraphicsDropShadowEffect (primary glow) — opacity не вешаем,
чтобы не съесть свечение.
"""
from __future__ import annotations

from PySide6.QtCore import QAbstractAnimation, QEasingCurve, QEvent, QObject, QPropertyAnimation
from PySide6.QtWidgets import QGraphicsDropShadowEffect, QGraphicsOpacityEffect, QWidget


class _HoverPressFilter(QObject):
    """Лёгкий dip opacity на hover/press. Во время busy — молчит."""

    def __init__(self, widget: QWidget) -> None:
        super().__init__(widget)
        self._w = widget
        self.busy = False
        self._pressed = False
        fx = widget.graphicsEffect()
        if isinstance(fx, QGraphicsDropShadowEffect):
            self._fx = None  # primary glow важнее
        elif isinstance(fx, QGraphicsOpacityEffect):
            self._fx = fx
        else:
            fx = QGraphicsOpacityEffect(widget)
            fx.setOpacity(1.0)
            widget.setGraphicsEffect(fx)
            self._fx = fx
        self._anim = None
        if self._fx is not None:
            self._anim = QPropertyAnimation(self._fx, b"opacity", self)
            self._anim.setDuration(150)
            self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        if obj is not self._w or self.busy or self._fx is None or self._anim is None:
            return False
        t = event.type()
        if t == QEvent.Type.Enter:
            if not self._pressed:
                self._to(0.88)
        elif t == QEvent.Type.Leave:
            self._pressed = False
            self._to(1.0)
        elif t == QEvent.Type.MouseButtonPress:
            self._pressed = True
            self._to(0.68)
        elif t == QEvent.Type.MouseButtonRelease:
            self._pressed = False
            self._to(0.88 if self._w.underMouse() else 1.0)
        elif t == QEvent.Type.EnabledChange:
            if not self._w.isEnabled():
                self._anim.stop()
                self._fx.setOpacity(1.0)
        return False

    def _to(self, value: float) -> None:
        if self._fx is None or self._anim is None:
            return
        self._anim.stop()
        self._anim.setStartValue(float(self._fx.opacity()))
        self._anim.setEndValue(value)
        self._anim.start()


class BusyPulse(QObject):
    """Дыхание opacity пока операция идёт."""

    def __init__(self, widget: QWidget, parent: QObject | None = None) -> None:
        super().__init__(parent or widget)
        self._w = widget
        fx = widget.graphicsEffect()
        if isinstance(fx, QGraphicsDropShadowEffect):
            self._fx = None
            self._anim = None
        elif isinstance(fx, QGraphicsOpacityEffect):
            self._fx = fx
            self._anim = QPropertyAnimation(self._fx, b"opacity", self)
        else:
            fx = QGraphicsOpacityEffect(widget)
            fx.setOpacity(1.0)
            widget.setGraphicsEffect(fx)
            self._fx = fx
            self._anim = QPropertyAnimation(self._fx, b"opacity", self)
        if self._anim is not None:
            self._anim.setDuration(850)
            self._anim.setStartValue(1.0)
            self._anim.setEndValue(0.40)
            self._anim.setEasingCurve(QEasingCurve.Type.InOutSine)
            self._anim.setLoopCount(-1)
        self._filter: _HoverPressFilter | None = getattr(widget, "_motion_filter", None)

    def start(self) -> None:
        if self._filter is not None:
            self._filter.busy = True
        if self._anim is None or self._fx is None:
            return
        if self._anim.state() != QAbstractAnimation.State.Running:
            self._anim.stop()
            self._fx.setOpacity(1.0)
            self._anim.start()

    def stop(self) -> None:
        if self._anim is not None and self._fx is not None:
            self._anim.stop()
            self._fx.setOpacity(1.0)
        if self._filter is not None:
            self._filter.busy = False


def attach_button_motion(btn: QWidget) -> _HoverPressFilter:
    """Повесить hover/press на кнопку. Повторный вызов безопасен."""
    existing = getattr(btn, "_motion_filter", None)
    if isinstance(existing, _HoverPressFilter):
        return existing
    filt = _HoverPressFilter(btn)
    btn.installEventFilter(filt)
    btn._motion_filter = filt  # noqa: SLF001 — держим ссылку от GC
    return filt


def attach_many(*buttons: QWidget | None) -> None:
    for btn in buttons:
        if btn is not None:
            attach_button_motion(btn)
