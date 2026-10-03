"""Микро-анимации кнопок (слой G): hover/press + busy pulse.

Без Lottie и без CSS keyframes — только QPropertyAnimation на opacity.
Если на кнопке уже QGraphicsDropShadowEffect (primary glow) — opacity не вешаем,
чтобы не съесть свечение.

Смена экранов разного размера: fade_center_transition (fade-out → resize+center → fade-in).
morph_widget_geometry оставлен как архив (у края кривит — не канон).
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
from PySide6.QtGui import QCursor, QGuiApplication
from PySide6.QtWidgets import (
    QApplication,
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


def _screen_for_widget_frame(frame: QRect):
    """Экран с макс. пересечением рамы; если ни одного — primary."""
    best = None
    best_area = 0
    for screen in QGuiApplication.screens():
        inter = frame.intersected(screen.availableGeometry())
        area = inter.width() * inter.height()
        if area > best_area:
            best_area = area
            best = screen
    if best is not None and best_area > 0:
        return best
    center = frame.center()
    for screen in QGuiApplication.screens():
        if screen.geometry().contains(center):
            return screen
    app = QApplication.instance()
    if app is not None:
        ps = app.primaryScreen()
        if ps is not None:
            return ps
    screens = QGuiApplication.screens()
    return screens[0] if screens else None


def center_widget_on_screen(widget: QWidget) -> None:
    """Поставить окно в центр availableGeometry текущего экрана."""
    screen = widget.screen()
    if screen is None:
        screen = _screen_for_widget_frame(widget.frameGeometry())
    if screen is None:
        app = QApplication.instance()
        screen = app.primaryScreen() if app is not None else None
    if screen is None:
        return
    avail = screen.availableGeometry()
    frame = widget.frameGeometry()
    frame.moveCenter(avail.center())
    widget.move(frame.topLeft())


def _screen_under_cursor():
    """Экран под курсором, иначе primary."""
    try:
        scr = QGuiApplication.screenAt(QCursor.pos())
    except Exception:
        scr = None
    if scr is not None:
        return scr
    app = QApplication.instance()
    if app is not None:
        return app.primaryScreen()
    screens = QGuiApplication.screens()
    return screens[0] if screens else None


def force_widget_on_cursor_screen(widget: QWidget, *, shrink: bool = True) -> None:
    """Всегда центр на монитор под курсором (диалоги с отравленным QSettings)."""
    if widget.isMaximized() or widget.isFullScreen():
        return
    screen = _screen_under_cursor()
    if screen is None:
        return
    avail = screen.availableGeometry()
    if shrink:
        max_w = max(320, avail.width() - 24)
        max_h = max(240, avail.height() - 24)
        w = min(max(widget.width(), 320), max_w)
        h = min(max(widget.height(), 240), max_h)
        widget.resize(w, h)
    frame = widget.frameGeometry()
    # Если frame ещё 0×0 — двигаем по geometry виджета
    if frame.width() < 32 or frame.height() < 32:
        geo = widget.geometry()
        x = avail.left() + max(0, (avail.width() - geo.width()) // 2)
        y = avail.top() + max(0, (avail.height() - geo.height()) // 2)
        widget.setGeometry(x, y, geo.width(), geo.height())
        return
    frame.moveCenter(avail.center())
    widget.move(frame.topLeft())
    frame = widget.frameGeometry()
    fx, fy = _frame_fit_top_left(
        avail, frame.width(), frame.height(), frame.x(), frame.y()
    )
    dx = widget.x() - frame.x()
    dy = widget.y() - frame.y()
    widget.move(fx + dx, fy + dy)


def ensure_widget_on_screen(
    widget: QWidget, *, shrink: bool = True, min_visible_frac: float = 0.4
) -> None:
    """Сдвинуть/ужать окно; если почти вне экрана — центр на монитор под курсором."""
    if widget.isMaximized() or widget.isFullScreen():
        return
    frame = widget.frameGeometry()
    area = max(1, frame.width() * frame.height())
    best_vis = 0
    for scr in QGuiApplication.screens():
        inter = frame.intersected(scr.availableGeometry())
        best_vis = max(best_vis, inter.width() * inter.height())
    # Слабый кусок / мёртвый монитор в QSettings → не «подтягивать», а центрировать
    if best_vis <= 0 or best_vis < area * max(0.05, min(1.0, min_visible_frac)):
        force_widget_on_cursor_screen(widget, shrink=shrink)
        return
    screen = _screen_for_widget_frame(frame)
    if screen is None:
        screen = _screen_under_cursor()
    if screen is None:
        return
    avail = screen.availableGeometry()
    if shrink:
        max_w = max(320, avail.width() - 16)
        max_h = max(240, avail.height() - 16)
        if widget.width() > max_w or widget.height() > max_h:
            widget.resize(min(widget.width(), max_w), min(widget.height(), max_h))
            frame = widget.frameGeometry()
    fx, fy = _frame_fit_top_left(avail, frame.width(), frame.height(), frame.x(), frame.y())
    dx = widget.x() - frame.x()
    dy = widget.y() - frame.y()
    widget.move(fx + dx, fy + dy)


def fade_window_opacity(
    widget: QWidget,
    end_opacity: float,
    *,
    duration_ms: int = 180,
    on_finished: Callable[[], None] | None = None,
) -> QPropertyAnimation:
    """Анимация windowOpacity (top-level)."""
    anim = QPropertyAnimation(widget, b"windowOpacity", widget)
    anim.setDuration(max(1, int(duration_ms)))
    anim.setStartValue(float(widget.windowOpacity()))
    anim.setEndValue(float(end_opacity))
    anim.setEasingCurve(QEasingCurve.Type.OutCubic)
    if on_finished is not None:
        anim.finished.connect(on_finished)
    anim.start(QAbstractAnimation.DeletionPolicy.KeepWhenStopped)
    return anim


def fade_center_transition(
    widget: QWidget,
    apply_mid: Callable[[], None],
    *,
    duration_out_ms: int = 160,
    duration_in_ms: int = 180,
    on_finished: Callable[[], None] | None = None,
) -> QPropertyAnimation:
    """Fade-out → apply_mid (resize/center/контент) → fade-in.

    Канон переходов SR (вариант 3 превью window-transition-types.html).
    Пока окно невидимо — можно безопасно менять size/flags/stack.
    """
    held: dict[str, QPropertyAnimation | None] = {"anim": None}

    def _fade_in() -> None:
        widget.setWindowOpacity(0.0)
        try:
            apply_mid()
        except Exception:
            widget.setWindowOpacity(1.0)
            if on_finished is not None:
                on_finished()
            return
        center_widget_on_screen(widget)
        widget.setWindowOpacity(0.0)

        def _done() -> None:
            widget.setWindowOpacity(1.0)
            if on_finished is not None:
                on_finished()

        held["anim"] = fade_window_opacity(
            widget, 1.0, duration_ms=duration_in_ms, on_finished=_done
        )

    if float(widget.windowOpacity()) <= 0.05:
        _fade_in()
        assert held["anim"] is not None
        return held["anim"]

    held["anim"] = fade_window_opacity(
        widget, 0.0, duration_ms=duration_out_ms, on_finished=_fade_in
    )
    return held["anim"]


def morph_widget_geometry(
    widget: QWidget,
    end_size: QSize,
    *,
    duration_ms: int = 300,
    on_finished: Callable[[], None] | None = None,
) -> QPropertyAnimation:
    """Архив: morph size+pos. У края кривит — не использовать для SR shell."""
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
