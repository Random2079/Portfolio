"""Микро-анимации кнопок (слой G): hover/press + busy pulse.

Без Lottie и без CSS keyframes — только QPropertyAnimation на opacity.
Если на кнопке уже QGraphicsDropShadowEffect (primary glow) — opacity не вешаем,
чтобы не съесть свечение.

Смена экранов разного размера: morph_widget_geometry (size+pos, без телепорта у края).
"""
from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import (
    QAbstractAnimation,
    QEasingCurve,
    QEvent,
    QObject,
    QPropertyAnimation,
    QRect,
    QSize,
)
from PySide6.QtWidgets import (
    QGraphicsDropShadowEffect,
    QGraphicsOpacityEffect,
    QWidget,
)


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


def _frame_fit_top_left(
    avail,
    frame_w: int,
    frame_h: int,
    prefer_x: int,
    prefer_y: int,
) -> tuple[int, int]:
    """Top-left рамы окна, чтобы frame_w×frame_h влез в availableGeometry."""
    if frame_w <= avail.width():
        x = max(avail.left(), min(prefer_x, avail.left() + avail.width() - frame_w))
    else:
        x = avail.left()
    if frame_h <= avail.height():
        y = max(avail.top(), min(prefer_y, avail.top() + avail.height() - frame_h))
    else:
        y = avail.top()
    return x, y


def morph_widget_geometry(
    widget: QWidget,
    end_size: QSize,
    *,
    duration_ms: int = 300,
    on_finished: Callable[[], None] | None = None,
) -> QPropertyAnimation:
    """Плавный ресайз+сдвиг: растёт/сжимается и сразу едет в место, где влезает.

    Иначе при окне у края size-only анимация уходит за экран, а _ensure_* телепортирует.
    """
    from PySide6.QtWidgets import QApplication

    screen = widget.screen()
    if screen is None:
        app = QApplication.instance()
        screen = app.primaryScreen() if app is not None else None

    start_geo = QRect(widget.geometry())
    frame = widget.frameGeometry()
    chrome_w = max(0, frame.width() - start_geo.width())
    chrome_h = max(0, frame.height() - start_geo.height())
    dx = start_geo.x() - frame.x()
    dy = start_geo.y() - frame.y()

    end_frame_w = end_size.width() + chrome_w
    end_frame_h = end_size.height() + chrome_h
    if screen is not None:
        avail = screen.availableGeometry()
        fx, fy = _frame_fit_top_left(
            avail, end_frame_w, end_frame_h, frame.x(), frame.y()
        )
    else:
        fx, fy = frame.x(), frame.y()

    end_geo = QRect(fx + dx, fy + dy, end_size.width(), end_size.height())

    widget.setMinimumSize(0, 0)
    widget.setMaximumSize(16777215, 16777215)
    anim = QPropertyAnimation(widget, b"geometry", widget)
    anim.setDuration(duration_ms)
    anim.setStartValue(start_geo)
    anim.setEndValue(end_geo)
    anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    def _done() -> None:
        widget.setFixedSize(end_size)
        widget.move(end_geo.topLeft())
        if on_finished is not None:
            on_finished()

    anim.finished.connect(_done)
    anim.start(QAbstractAnimation.DeletionPolicy.KeepWhenStopped)
    return anim


# alias на старое имя
def morph_widget_size(
    widget: QWidget,
    end_size: QSize,
    *,
    duration_ms: int = 300,
    on_finished: Callable[[], None] | None = None,
) -> QPropertyAnimation:
    return morph_widget_geometry(
        widget, end_size, duration_ms=duration_ms, on_finished=on_finished
    )
