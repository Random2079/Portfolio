"""
Windows SMTC (System Media Transport Controls) для overlay «Фон».

Зачем: кнопки наушников Windows отдаёт «медиа-сессии», а не RegisterHotKey.
Chrome/yomi.to тоже вешает сессию → без SMTC наушники уходят в аниме.
С SMTC Фон заявляет «сейчас играю» и чаще перехватывает play/next/prev.

Зависимости (опц.): winrt-Windows.Media (+ Foundation). Нет пакета → SMTC выкл,
остаются только VK_MEDIA_* RegisterHotKey.
"""
from __future__ import annotations

import ctypes
import logging
import sys
from ctypes import wintypes
from typing import Callable

log = logging.getLogger("overlay_smtc")

# ISystemMediaTransportControlsInterop
_IID_SMTC_INTEROP = "{ddb0472d-c911-4a1f-86d9-dc3d71a95f5a}"
# ISystemMediaTransportControls (default interface of runtimeclass)
_IID_SMTC = "{99FA3FF4-1742-42A6-902E-8B5EBB76F0AD}"

RO_INIT_MULTITHREADED = 1

_HAS_WINRT = False
try:
    from winrt.windows.media import (  # type: ignore
        MediaPlaybackStatus,
        MediaPlaybackType,
        SystemMediaTransportControls,
        SystemMediaTransportControlsButton,
    )
    from winrt.runtime import init_apartment, ApartmentType  # type: ignore

    _HAS_WINRT = True
except Exception as exc:  # noqa: BLE001
    log.debug("winrt SMTC unavailable: %s", exc)
    MediaPlaybackStatus = None  # type: ignore
    MediaPlaybackType = None  # type: ignore
    SystemMediaTransportControls = None  # type: ignore
    SystemMediaTransportControlsButton = None  # type: ignore


def smtc_available() -> bool:
    return bool(_HAS_WINRT and sys.platform == "win32")


def _guid(s: str) -> ctypes.c_byte * 16:
    """'{'uuid'}' → GUID bytes (COM / WinRT layout)."""
    import uuid

    u = uuid.UUID(s.strip("{}"))
    return (ctypes.c_byte * 16).from_buffer_copy(u.bytes_le)


def _get_smtc_for_window(hwnd: int):
    """Win32 HWND → SystemMediaTransportControls via interop."""
    if not smtc_available() or not hwnd:
        return None

    ole32 = ctypes.windll.ole32
    combase = ctypes.windll.LoadLibrary("combase.dll")

    # RoInitialize may already be done by Qt/winrt
    try:
        init_apartment(ApartmentType.MTA)
    except Exception:
        pass
    try:
        RoInitialize = ctypes.WINFUNCTYPE(ctypes.HRESULT, ctypes.c_uint)(
            ("RoInitialize", combase)
        )
        hr = RoInitialize(RO_INIT_MULTITHREADED)
        # S_OK=0, S_FALSE=1, RPC_E_CHANGED_MODE=0x80010106 — ок если уже инициализировано
        if hr not in (0, 1) and (hr & 0xFFFFFFFF) != 0x80010106:
            log.warning("RoInitialize hr=0x%08X", hr & 0xFFFFFFFF)
    except Exception as exc:
        log.debug("RoInitialize: %s", exc)

    WindowsCreateString = ctypes.WINFUNCTYPE(
        ctypes.HRESULT,
        wintypes.LPCWSTR,
        ctypes.c_uint32,
        ctypes.POINTER(ctypes.c_void_p),
    )(("WindowsCreateString", combase))
    RoGetActivationFactory = ctypes.WINFUNCTYPE(
        ctypes.HRESULT,
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_byte * 16),
        ctypes.POINTER(ctypes.c_void_p),
    )(("RoGetActivationFactory", combase))

    hstring = ctypes.c_void_p()
    class_name = "Windows.Media.SystemMediaTransportControls"
    hr = WindowsCreateString(class_name, len(class_name), ctypes.byref(hstring))
    if hr != 0:
        log.warning("WindowsCreateString hr=0x%08X", hr & 0xFFFFFFFF)
        return None

    interop = ctypes.c_void_p()
    iid_interop = _guid(_IID_SMTC_INTEROP)
    hr = RoGetActivationFactory(hstring, ctypes.byref(iid_interop), ctypes.byref(interop))
    if hr != 0 or not interop.value:
        log.warning("RoGetActivationFactory hr=0x%08X", hr & 0xFFFFFFFF)
        return None

    # IInspectable: QueryInterface=0, AddRef=1, Release=2, GetForWindow=3 (on interop)
    vtable = ctypes.cast(interop, ctypes.POINTER(ctypes.c_void_p)).contents.value
    get_for_window_ptr = ctypes.cast(
        vtable + 3 * ctypes.sizeof(ctypes.c_void_p),
        ctypes.POINTER(ctypes.c_void_p),
    ).contents.value

    GetForWindow = ctypes.WINFUNCTYPE(
        ctypes.HRESULT,
        ctypes.c_void_p,
        wintypes.HWND,
        ctypes.POINTER(ctypes.c_byte * 16),
        ctypes.POINTER(ctypes.c_void_p),
    )(get_for_window_ptr)

    smtc_ptr = ctypes.c_void_p()
    iid_smtc = _guid(_IID_SMTC)
    hr = GetForWindow(
        interop,
        wintypes.HWND(int(hwnd)),
        ctypes.byref(iid_smtc),
        ctypes.byref(smtc_ptr),
    )
    if hr != 0 or not smtc_ptr.value:
        log.warning("GetForWindow hr=0x%08X hwnd=%s", hr & 0xFFFFFFFF, hwnd)
        return None

    try:
        return SystemMediaTransportControls._from(smtc_ptr.value)  # type: ignore[attr-defined]
    except Exception as exc:
        log.warning("SMTC._from failed: %s", exc)
        return None


class OverlaySmtc:
    """Тонкая обёртка: play/pause/next/prev с наушников → колбэки на Qt-потоке."""

    def __init__(self) -> None:
        self._smtc = None
        self._token = None
        self._on_play_pause: Callable[[], None] | None = None
        self._on_next: Callable[[], None] | None = None
        self._on_prev: Callable[[], None] | None = None
        self._title = "Фон — overlay"

    @property
    def active(self) -> bool:
        return self._smtc is not None

    def bind(
        self,
        hwnd: int,
        *,
        on_play_pause: Callable[[], None],
        on_next: Callable[[], None],
        on_prev: Callable[[], None],
    ) -> bool:
        if not smtc_available():
            return False
        self._on_play_pause = on_play_pause
        self._on_next = on_next
        self._on_prev = on_prev
        if self._smtc is not None:
            return True
        smtc = _get_smtc_for_window(int(hwnd))
        if smtc is None:
            return False
        try:
            smtc.is_enabled = True
            smtc.is_play_enabled = True
            smtc.is_pause_enabled = True
            smtc.is_next_enabled = True
            smtc.is_previous_enabled = True
            smtc.is_stop_enabled = False
            # Display
            updater = smtc.display_updater
            updater.type = MediaPlaybackType.MUSIC
            updater.music_properties.title = self._title
            updater.music_properties.artist = "Subtitle Ripper Pro"
            updater.update()

            def _on_button(_sender, args) -> None:
                try:
                    btn = args.button
                except Exception:
                    return
                if btn == SystemMediaTransportControlsButton.PLAY or btn == SystemMediaTransportControlsButton.PAUSE:
                    if self._on_play_pause:
                        self._on_play_pause()
                elif btn == SystemMediaTransportControlsButton.NEXT:
                    if self._on_next:
                        self._on_next()
                elif btn == SystemMediaTransportControlsButton.PREVIOUS:
                    if self._on_prev:
                        self._on_prev()

            self._token = smtc.add_button_pressed(_on_button)
            self._smtc = smtc
            log.info("SMTC bound hwnd=%s", hwnd)
            return True
        except Exception as exc:
            log.warning("SMTC bind failed: %s", exc)
            self._smtc = None
            return False

    def set_playing(self, playing: bool, *, title: str | None = None) -> None:
        if self._smtc is None:
            return
        try:
            if title:
                self._title = title
                updater = self._smtc.display_updater
                updater.type = MediaPlaybackType.MUSIC
                updater.music_properties.title = self._title[:120]
                updater.update()
            self._smtc.playback_status = (
                MediaPlaybackStatus.PLAYING if playing else MediaPlaybackStatus.PAUSED
            )
        except Exception as exc:
            log.debug("SMTC set_playing: %s", exc)

    def clear(self) -> None:
        if self._smtc is None:
            return
        try:
            self._smtc.playback_status = MediaPlaybackStatus.CLOSED
            self._smtc.is_enabled = False
        except Exception:
            pass
        self._smtc = None
        self._token = None
