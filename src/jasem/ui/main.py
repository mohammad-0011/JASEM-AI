"""Qt application bootstrap."""

from __future__ import annotations

import logging
import sys

from PySide6.QtCore import QUrl, Qt
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from .. import paths
from ..config import AppConfig, save_config
from ..orchestrator import AssistantCore
from .bridge import AppBridge

log = logging.getLogger("jasem.ui")


def _make_icon(color: str = "#22d3ee") -> QIcon:
    pm = QPixmap(64, 64)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(color))
    p.drawEllipse(8, 8, 48, 48)
    p.setBrush(QColor("#050a14"))
    p.drawEllipse(20, 20, 24, 24)
    p.end()
    return QIcon(pm)


def run_ui(core: AssistantCore, cfg: AppConfig) -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("JASEM")
    app.setOrganizationName("JASEM")
    app.setWindowIcon(_make_icon())
    if not cfg.ui.close_to_tray:
        app.setQuitOnLastWindowClosed(True)

    bridge = AppBridge(core, cfg)
    engine = _qml_engine()
    engine.rootContext().setContextProperty("bridge", bridge)
    qml_file = paths.QML_DIR / "Main.qml"
    engine.load(QUrl.fromLocalFile(str(qml_file)))
    if not engine.rootObjects():
        log.error("QML failed to load: %s", qml_file)
        return 1
    window = engine.rootObjects()[0]
    window.flags = window.flags()
    if cfg.ui.always_on_top:
        window.flags |= Qt.WindowType.WindowStaysOnTopHint

    tray: QSystemTrayIcon | None = None
    if QSystemTrayIcon.isSystemTrayAvailable():
        tray = QSystemTrayIcon(_make_icon(), parent=app)
        tray.setToolTip("جاسم — دستیار صوتی")
        menu = QMenu()
        act_show = QAction("نمایش جاسم")
        act_show.triggered.connect(lambda: (window.show(), window.raise_()))
        act_mute = QAction("بی‌صدا / فعال")
        act_mute.triggered.connect(bridge.toggleMic)
        act_quit = QAction("خروج کامل")
        act_quit.triggered.connect(app.quit)
        menu.addAction(act_show)
        menu.addAction(act_mute)
        menu.addSeparator()
        menu.addAction(act_quit)
        tray.setContextMenu(menu)
        tray.activated.connect(
            lambda reason: window.show() if reason == QSystemTrayIcon.ActivationReason.Trigger else None
        )
        tray.show()

    core.start()

    # -- global hotkeys (configurable, Win32 RegisterHotKey) -----------------
    hotkeys = None
    try:
        from ..hotkeys import HotkeyManager

        hotkeys = HotkeyManager()
        ok_ptt = hotkeys.register(cfg.ui.hotkey_ptt, bridge.pushToTalk)
        ok_mute = hotkeys.register(cfg.ui.hotkey_mute, bridge.toggleMic)
        if ok_ptt or ok_mute:
            hotkeys.start()
            parts = []
            if ok_ptt:
                parts.append(f"{cfg.ui.hotkey_ptt}=مکالمه")
            if ok_mute:
                parts.append(f"{cfg.ui.hotkey_mute}=بی‌صدا")
            log.info("hotkeys active: %s", "، ".join(parts))
    except Exception:
        log.exception("hotkey setup failed; continuing without global shortcuts")
        hotkeys = None

    def shutdown() -> None:
        if hotkeys is not None:
            try:
                hotkeys.stop()
            except Exception:
                log.exception("hotkey teardown failed")
        try:
            core.shutdown()
        finally:
            save_config(cfg)

    app.aboutToQuit.connect(shutdown)
    window.show()
    return app.exec()


def _qml_engine():
    from PySide6.QtQml import QQmlApplicationEngine

    return QQmlApplicationEngine()
