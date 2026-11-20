"""Project Golu: Floating Siri-Like Interactive Voice Assistant HUD (PyQt6).
Modern, translucent glassmorphism widget that pops up like Siri/Cortana on Windows:
- Floating pill/card with glowing pulse animation when listening
- Real-time display of user's speech transcript
- Formatted presentation of Golu's answer (Vault, RAG, Web Search, Brain)
- Interactive controls: Mic trigger, Open Web Dashboard, Emergency Stop
- Draggable, stays on top, rounded glassmorphic styling
"""

import sys
import os
import webbrowser
import logging
from typing import Optional

from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject, QPoint
from PyQt6.QtGui import QFont, QColor, QPainter, QBrush, QPen, QLinearGradient
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QFrame, QGraphicsDropShadowEffect,
    QProgressBar, QScrollArea
)

logger = logging.getLogger("golu.siri_hud")


class SiriHUDCommunicator(QObject):
    """Bridge for cross-thread communication to the Siri HUD."""
    show_signal = pyqtSignal()
    hide_signal = pyqtSignal()
    listening_signal = pyqtSignal(str)   # Status text e.g. "Listening..."
    transcript_signal = pyqtSignal(str)  # User question e.g. "What is quantum computing?"
    answer_signal = pyqtSignal(str, str) # (Answer text, source e.g. "internet_search")
    close_signal = pyqtSignal()


# Global communicator instance
siri_communicator = SiriHUDCommunicator()


class FloatingSiriHUD(QWidget):
    """Floating Siri-like glassmorphic voice assistant window."""

    def __init__(self, communicator: Optional[SiriHUDCommunicator] = None):
        super().__init__()
        self.comm = communicator or siri_communicator
        self._drag_pos = None
        self._pulse_step = 0
        self._is_listening = False

        self._setup_window()
        self._setup_ui()
        self._connect_signals()

        # Pulse timer for animated glowing Siri orb
        self.pulse_timer = QTimer(self)
        self.pulse_timer.timeout.connect(self._animate_pulse)
        self.pulse_timer.start(50)

    def _setup_window(self):
        """Sets up frameless, always-on-top, translucent window."""
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.resize(520, 280)
        self.setMinimumSize(460, 240)

        # Center horizontally at the bottom of the screen
        screen = QApplication.primaryScreen()
        if screen:
            screen_geo = screen.availableGeometry()
            x = (screen_geo.width() - self.width()) // 2
            y = screen_geo.height() - self.height() - 40
            self.move(x, y)

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)

        # Outer Glass Container
        self.container = QFrame(self)
        self.container.setObjectName("siriContainer")
        self.container.setStyleSheet("""
            QFrame#siriContainer {
                background: rgba(11, 17, 32, 0.95);
                border: 2px solid rgba(56, 189, 248, 0.5);
                border-radius: 20px;
            }
        """)

        # Drop shadow effect
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(30)
        shadow.setColor(QColor(0, 0, 0, 220))
        shadow.setOffset(0, 10)
        self.container.setGraphicsEffect(shadow)

        container_layout = QVBoxLayout(self.container)
        container_layout.setContentsMargins(18, 14, 18, 14)
        container_layout.setSpacing(10)

        # Header bar
        header_layout = QHBoxLayout()
        header_layout.setSpacing(10)

        # Siri Orb Icon indicator
        self.orb_label = QLabel("✨", self.container)
        self.orb_label.setStyleSheet("font-size: 18px;")

        self.title_label = QLabel("GOLU VOICE ASSISTANT", self.container)
        self.title_label.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        self.title_label.setStyleSheet("color: #38bdf8; letter-spacing: 1.5px;")

        self.badge_label = QLabel("IDLE", self.container)
        self.badge_label.setStyleSheet("""
            background: rgba(56, 189, 248, 0.2);
            color: #38bdf8;
            font-size: 10px;
            font-weight: bold;
            padding: 2px 8px;
            border-radius: 10px;
            border: 1px solid rgba(56, 189, 248, 0.4);
        """)

        header_layout.addWidget(self.orb_label)
        header_layout.addWidget(self.title_label)
        header_layout.addWidget(self.badge_label)
        header_layout.addStretch()

        # Dashboard Button
        self.btn_dashboard = QPushButton("📊 Dashboard", self.container)
        self.btn_dashboard.setStyleSheet("""
            QPushButton {
                background: rgba(56, 189, 248, 0.15);
                color: #38bdf8;
                border: 1px solid rgba(56, 189, 248, 0.4);
                border-radius: 8px;
                padding: 4px 10px;
                font-size: 11px;
                font-weight: 600;
            }
            QPushButton:hover {
                background: rgba(56, 189, 248, 0.35);
                color: #ffffff;
            }
        """)
        self.btn_dashboard.clicked.connect(self._open_dashboard)

        # Close Button
        self.btn_close = QPushButton("✕", self.container)
        self.btn_close.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #94a3b8;
                border: none;
                font-size: 14px;
                font-weight: bold;
                padding: 2px 6px;
            }
            QPushButton:hover {
                color: #f87171;
            }
        """)
        self.btn_close.clicked.connect(self.hide)

        header_layout.addWidget(self.btn_dashboard)
        header_layout.addWidget(self.btn_close)
        container_layout.addLayout(header_layout)

        # Transcript Box (User's Question)
        self.transcript_label = QLabel("Say 'Hey Golu' or press [Ctrl+Alt+A] to talk...", self.container)
        self.transcript_label.setFont(QFont("Segoe UI", 12, QFont.Weight.Medium))
        self.transcript_label.setStyleSheet("color: #e2e8f0; padding: 4px 0;")
        self.transcript_label.setWordWrap(True)
        container_layout.addWidget(self.transcript_label)

        # Answer Box (Golu's Response)
        self.answer_label = QLabel("I'm ready. Ask me anything, search the internet, or fill your forms!", self.container)
        self.answer_label.setFont(QFont("Segoe UI", 11))
        self.answer_label.setStyleSheet("""
            color: #94a3b8;
            background: rgba(15, 23, 42, 0.6);
            border-radius: 10px;
            padding: 8px 12px;
            border: 1px solid rgba(148, 163, 184, 0.15);
        """)
        self.answer_label.setWordWrap(True)
        container_layout.addWidget(self.answer_label)

        # Bottom Bar: Status + Mic Control + Stop Button
        bottom_layout = QHBoxLayout()
        bottom_layout.setSpacing(10)

        self.status_label = QLabel("Ready • Mic Active", self.container)
        self.status_label.setStyleSheet("color: #64748b; font-size: 11px;")
        bottom_layout.addWidget(self.status_label)
        bottom_layout.addStretch()

        # Mic Trigger Button
        self.btn_mic = QPushButton("🎤 Talk to Golu", self.container)
        self.btn_mic.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0284c7, stop:1 #06b6d4);
                color: #ffffff;
                border: none;
                border-radius: 10px;
                padding: 6px 14px;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0369a1, stop:1 #0891b2);
            }
        """)
        self.btn_mic.clicked.connect(self._trigger_mic)
        bottom_layout.addWidget(self.btn_mic)

        # Stop Golu Button
        self.btn_stop = QPushButton("⏹️ Stop Golu", self.container)
        self.btn_stop.setStyleSheet("""
            QPushButton {
                background: rgba(239, 68, 68, 0.15);
                color: #f87171;
                border: 1px solid rgba(239, 68, 68, 0.35);
                border-radius: 10px;
                padding: 6px 12px;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton:hover {
                background: rgba(239, 68, 68, 0.3);
                color: #ffffff;
            }
        """)
        self.btn_stop.clicked.connect(self._stop_golu)
        bottom_layout.addWidget(self.btn_stop)

        container_layout.addLayout(bottom_layout)
        main_layout.addWidget(self.container)

    def _connect_signals(self):
        self.comm.show_signal.connect(self._on_show)
        self.comm.hide_signal.connect(self.hide)
        self.comm.listening_signal.connect(self._on_listening)
        self.comm.transcript_signal.connect(self._on_transcript)
        self.comm.answer_signal.connect(self._on_answer)
        self.comm.close_signal.connect(self.close)

    def _on_show(self):
        self.show()
        self.raise_()
        self.activateWindow()

    def _on_listening(self, msg: str):
        self._is_listening = True
        self.show()
        self.badge_label.setText("LISTENING")
        self.badge_label.setStyleSheet("""
            background: rgba(234, 179, 8, 0.2);
            color: #facc15;
            font-size: 10px;
            font-weight: bold;
            padding: 2px 8px;
            border-radius: 10px;
            border: 1px solid rgba(234, 179, 8, 0.4);
        """)
        self.status_label.setText(msg or "Listening for your voice...")
        self.transcript_label.setText("Listening...")
        self.answer_label.setText("Speak now...")

    def _on_transcript(self, text: str):
        self.show()
        self.badge_label.setText("THINKING")
        self.badge_label.setStyleSheet("""
            background: rgba(192, 132, 252, 0.2);
            color: #c084fc;
            font-size: 10px;
            font-weight: bold;
            padding: 2px 8px;
            border-radius: 10px;
            border: 1px solid rgba(192, 132, 252, 0.4);
        """)
        self.transcript_label.setText(f"You: \"{text}\"")
        self.status_label.setText("Thinking & searching...")

    def _on_answer(self, answer: str, source: str):
        self._is_listening = False
        self.show()
        source_display = {
            "vault": "VAULT (<5ms)",
            "rag": "RESUME RAG",
            "internet_search": "WEB SEARCH",
            "local_llm": "CORE BRAIN"
        }.get(source, source.upper())

        self.badge_label.setText(source_display)
        self.badge_label.setStyleSheet("""
            background: rgba(52, 211, 153, 0.2);
            color: #34d399;
            font-size: 10px;
            font-weight: bold;
            padding: 2px 8px;
            border-radius: 10px;
            border: 1px solid rgba(52, 211, 153, 0.4);
        """)
        self.answer_label.setText(f"Golu: {answer}")
        self.status_label.setText(f"Answered via {source_display}")

    def _animate_pulse(self):
        """Creates dynamic Siri-like glowing pulse around the container border."""
        if self._is_listening:
            self._pulse_step = (self._pulse_step + 1) % 40
            alpha = int(120 + 80 * (self._pulse_step / 40.0 if self._pulse_step < 20 else (40 - self._pulse_step) / 20.0))
            self.container.setStyleSheet(f"""
                QFrame#siriContainer {{
                    background: rgba(11, 17, 32, 0.95);
                    border: 2px solid rgba(56, 189, 248, {alpha / 255.0:.2f});
                    border-radius: 20px;
                }}
            """)

    def _trigger_mic(self):
        """User clicks the mic button on the HUD."""
        try:
            from backend.state_machine import state_machine
            state_machine.on_hotkey_assistant()
        except Exception as e:
            logger.error("Error triggering mic from HUD: %s", e)

    def _open_dashboard(self):
        """Opens http://127.0.0.1:8000/dashboard in default web browser."""
        webbrowser.open("http://127.0.0.1:8000/dashboard")

    def _stop_golu(self):
        """Emergency Stop button."""
        try:
            from backend.state_machine import state_machine, GoluMode
            state_machine.transition_to(GoluMode.KILL)
            self.hide()
        except Exception as e:
            logger.error("Error stopping Golu from HUD: %s", e)

    # Window Dragging handlers
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


def launch_siri_hud(communicator: Optional[SiriHUDCommunicator] = None) -> FloatingSiriHUD:
    """Helper to instantiate and show the Siri HUD."""
    hud = FloatingSiriHUD(communicator)
    hud.show()
    return hud


if __name__ == "__main__":
    app = QApplication(sys.argv)
    hud = launch_siri_hud()
    hud.comm.listening_signal.emit("Listening for 'Hey Golu'...")
    sys.exit(app.exec())
