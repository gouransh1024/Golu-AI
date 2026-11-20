"""Project Golu: Invisible Meeting Co-Pilot HUD (PyQt6).
Uses Windows 10/11 SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE) (0x00000011)
to render the HUD completely invisible to screen shares (Zoom, Google Meet, Teams, OBS).
The local user sees the HUD on screen; meeting attendees see only what is behind it.
"""

import sys
import os
import ctypes
from ctypes import wintypes
import logging
from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal, QObject
from PyQt6.QtGui import QFont, QColor
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QTextEdit, QPushButton, QFrame, QGraphicsDropShadowEffect
)

logger = logging.getLogger("golu.hud")

# Windows Display Affinity Constants
WDA_NONE = 0x00000000
WDA_MONITOR = 0x00000001
WDA_EXCLUDEFROMCAPTURE = 0x00000011  # Windows 10 2004+ and Windows 11


def apply_display_affinity(hwnd: int) -> bool:
    """Sets WDA_EXCLUDEFROMCAPTURE on the target window handle.
    Renders the window invisible to screen capture, screen recording, and video calls.
    """
    try:
        user32 = ctypes.windll.user32
        res = user32.SetWindowDisplayAffinity(
            wintypes.HWND(hwnd),
            wintypes.DWORD(WDA_EXCLUDEFROMCAPTURE)
        )
        return bool(res)
    except Exception as e:
        logger.error("Failed to apply SetWindowDisplayAffinity: %s", e)
        return False


class HUDCommunicator(QObject):
    """Thread-safe Qt signal bridge for updating HUD from background workers."""
    transcript_signal = pyqtSignal(str)
    answer_signal = pyqtSignal(str)
    status_signal = pyqtSignal(str)
    wipe_signal = pyqtSignal()
    toggle_signal = pyqtSignal()


class StealthHUDOverlay(QWidget):
    """Floating Glassmorphism Meeting Co-Pilot Overlay with Screen-Share Cloaking."""

    def __init__(self, communicator: Optional[HUDCommunicator] = None):
        super().__init__()
        self.communicator = communicator or HUDCommunicator()
        self.is_stealth_active: bool = False
        self._drag_pos = None

        self._setup_window_flags()
        self._setup_ui()
        self._connect_signals()

    def _setup_window_flags(self):
        """Configures frameless, always-on-top, semi-transparent tool window."""
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.resize(460, 520)
        self.setMinimumSize(360, 400)

    def _setup_ui(self):
        """Constructs modern dark glassmorphism interface."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)

        # Glass Container Frame
        self.container = QFrame(self)
        self.container.setObjectName("hudContainer")
        self.container.setStyleSheet("""
            QFrame#hudContainer {
                background: rgba(15, 23, 42, 0.94);
                border: 1px solid rgba(56, 189, 248, 0.35);
                border-radius: 14px;
            }
        """)
        
        # Shadow Effect
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(25)
        shadow.setColor(QColor(0, 0, 0, 180))
        shadow.setOffset(0, 8)
        self.container.setGraphicsEffect(shadow)

        container_layout = QVBoxLayout(self.container)
        container_layout.setContentsMargins(16, 14, 16, 14)
        container_layout.setSpacing(10)

        # Header Bar
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)

        self.title_label = QLabel("🛡️ GOLU CO-PILOT (STEALTH)")
        self.title_label.setStyleSheet("color: #38bdf8; font-weight: bold; font-size: 13px; letter-spacing: 0.5px;")

        self.badge_label = QLabel("CLOAKED")
        self.badge_label.setStyleSheet("""
            background: rgba(16, 185, 129, 0.2);
            color: #34d399;
            font-size: 10px;
            font-weight: bold;
            padding: 3px 7px;
            border-radius: 6px;
            border: 1px solid rgba(16, 185, 129, 0.4);
        """)

        header_layout.addWidget(self.title_label)
        header_layout.addStretch()
        header_layout.addWidget(self.badge_label)
        container_layout.addLayout(header_layout)

        # Live Transcript Box
        trans_label = QLabel("SPEAKER AUDIO TRANSCRIPT:")
        trans_label.setStyleSheet("color: #94a3b8; font-size: 10px; font-weight: bold;")
        container_layout.addWidget(trans_label)

        self.transcript_box = QTextEdit()
        self.transcript_box.setReadOnly(True)
        self.transcript_box.setPlaceholderText("Awaiting meeting audio via WASAPI Loopback...")
        self.transcript_box.setStyleSheet("""
            QTextEdit {
                background: rgba(30, 41, 59, 0.7);
                border: 1px solid rgba(148, 163, 184, 0.15);
                border-radius: 8px;
                color: #e2e8f0;
                font-size: 12px;
                padding: 6px;
                font-family: 'Segoe UI', sans-serif;
            }
        """)
        self.transcript_box.setMaximumHeight(140)
        container_layout.addWidget(self.transcript_box)

        # Co-Pilot Answer Suggestions Box
        ans_label = QLabel("REAL-TIME AI SUGGESTIONS:")
        ans_label.setStyleSheet("color: #38bdf8; font-size: 10px; font-weight: bold;")
        container_layout.addWidget(ans_label)

        self.answer_box = QTextEdit()
        self.answer_box.setReadOnly(True)
        self.answer_box.setPlaceholderText("Grounded answer bullets will appear here in < 1.5s...")
        self.answer_box.setStyleSheet("""
            QTextEdit {
                background: rgba(15, 23, 42, 0.85);
                border: 1px solid rgba(56, 189, 248, 0.25);
                border-radius: 8px;
                color: #f8fafc;
                font-size: 12.5px;
                line-height: 1.4;
                padding: 8px;
                font-family: 'Segoe UI', sans-serif;
            }
        """)
        container_layout.addWidget(self.answer_box)

        # Footer Shortcuts
        footer_label = QLabel("[Ctrl+Alt+H] Hide HUD  |  [Ctrl+Alt+X] Kill Switch")
        footer_label.setStyleSheet("color: #64748b; font-size: 10px; text-align: center;")
        footer_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        container_layout.addWidget(footer_label)

        main_layout.addWidget(self.container)

    def _connect_signals(self):
        """Connects communicator signals to UI slots."""
        self.communicator.transcript_signal.connect(self.update_transcript)
        self.communicator.answer_signal.connect(self.update_answer)
        self.communicator.status_signal.connect(self.update_status)
        self.communicator.wipe_signal.connect(self.wipe_and_hide)
        self.communicator.toggle_signal.connect(self.toggle_hud_visibility)

    def showEvent(self, event):
        """Applies WDA_EXCLUDEFROMCAPTURE immediately when window appears."""
        super().showEvent(event)
        hwnd = int(self.winId())
        self.is_stealth_active = apply_display_affinity(hwnd)
        if self.is_stealth_active:
            self.badge_label.setText("CLOAKED 🛡️")
            logger.info("Stealth HUD successfully cloaked with WDA_EXCLUDEFROMCAPTURE.")
        else:
            self.badge_label.setText("VISIBLE ⚠️")
            logger.warning("Stealth HUD display affinity could not be applied.")

    def update_transcript(self, text: str):
        """Appends new speaker transcription."""
        self.transcript_box.append(f"• {text.strip()}")

    def update_answer(self, answer_text: str):
        """Displays suggested AI answer."""
        self.answer_box.setHtml(f"<div style='color: #38bdf8;'><b>Suggested Response:</b></div><div>{answer_text.strip()}</div>")

    def update_status(self, status: str):
        self.title_label.setText(f"🛡️ GOLU CO-PILOT ({status})")

    def toggle_hud_visibility(self):
        """Toggles HUD visibility on/off for physical screen privacy."""
        if self.isVisible():
            self.hide()
        else:
            self.show()

    def wipe_and_hide(self):
        """Emergency Kill Switch handler: immediately clears buffers and hides in < 10ms."""
        self.transcript_box.clear()
        self.answer_box.clear()
        self.hide()
        logger.info("Stealth HUD wiped and hidden by emergency interrupt.")

    # Draggable Window support
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton and self._drag_pos is not None:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        self._drag_pos = None


def create_hud_app() -> tuple[QApplication, StealthHUDOverlay, HUDCommunicator]:
    """Helper to instantiate Qt app and Stealth HUD."""
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    communicator = HUDCommunicator()
    overlay = StealthHUDOverlay(communicator=communicator)
    return app, overlay, communicator


if __name__ == "__main__":
    app, hud, comm = create_hud_app()
    hud.show()
    comm.transcript_signal.emit("Can you explain how you optimized the VRAM for Golu?")
    comm.answer_signal.emit("• Partitioned memory strictly: Ollama LLM gets 2.6-3.3 GB VRAM.<br>• Faster-Whisper, embeddings, and TTS run 100% on CPU.<br>• Dynamic watchdog trims context if VRAM exceeds 3.75 GB.")
    sys.exit(app.exec())
