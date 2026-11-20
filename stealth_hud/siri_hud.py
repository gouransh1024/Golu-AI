"""Project Golu: Expandable Floating Logo & Siri Chat Window (PyQt6).
Features:
- Collapsed Mode: Cute, compact 64x64 floating circular Golu logo that sits on screen with a glowing ambient pulse
- Expanded Mode: Rich 380x480 glassmorphism chat window with message history, text typing, voice mic, and dashboard links
- Seamless toggle: Click logo or press [Ctrl+Alt+A] to expand; click minimize button to collapse back to logo
- Text + Voice dual-input: Type and press Enter to chat silently, or click the mic / say 'Hey Golu' to speak!
- Modern dark translucent glassmorphism, draggable anywhere, always-on-top
"""

import sys
import os
import webbrowser
import logging
import threading
from typing import Optional

from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject, QPoint, QSize
from PyQt6.QtGui import QFont, QColor, QPainter, QBrush, QPen, QLinearGradient, QPainterPath
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QFrame, QGraphicsDropShadowEffect,
    QLineEdit, QScrollArea, QStackedLayout
)

from backend.assistant import assistant
from backend.audio.golu_voice import voice_engine

logger = logging.getLogger("golu.siri_hud")


class SiriHUDCommunicator(QObject):
    """Bridge for cross-thread communication to the Siri HUD."""
    show_signal = pyqtSignal()
    hide_signal = pyqtSignal()
    expand_signal = pyqtSignal()
    collapse_signal = pyqtSignal()
    listening_signal = pyqtSignal(str)
    transcript_signal = pyqtSignal(str)
    answer_signal = pyqtSignal(str, str) # (answer, source)
    close_signal = pyqtSignal()


# Global communicator instance
siri_communicator = SiriHUDCommunicator()


class FloatingSiriHUD(QWidget):
    """Floating Logo & Siri Chat Window for Project Golu."""

    def __init__(self, communicator: Optional[SiriHUDCommunicator] = None):
        super().__init__()
        self.comm = communicator or siri_communicator
        self.is_expanded = False
        self._drag_pos = None
        self._pulse_step = 0
        self._is_listening = False

        self._setup_window()
        self._setup_ui()
        self._connect_signals()

        # Pulse timer for glowing ring
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
        self.resize(72, 72)

        # Position near bottom right
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            self.move(geo.width() - 100, geo.height() - 120)

    def _setup_ui(self):
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(4, 4, 4, 4)

        self.stacked_layout = QStackedLayout()
        self.main_layout.addLayout(self.stacked_layout)

        # ================= VIEW 0: MINI FLOATING LOGO =================
        self.logo_widget = QFrame(self)
        self.logo_widget.setObjectName("logoFrame")
        self.logo_widget.setFixedSize(64, 64)
        self.logo_widget.setCursor(Qt.CursorShape.PointingHandCursor)
        self.logo_widget.setStyleSheet("""
            QFrame#logoFrame {
                background: qradialgradient(cx:0.5, cy:0.5, radius:0.5, fx:0.3, fy:0.3, stop:0 #38bdf8, stop:0.8 #0284c7, stop:1 #0f172a);
                border: 2px solid #38bdf8;
                border-radius: 32px;
            }
        """)

        logo_layout = QVBoxLayout(self.logo_widget)
        logo_layout.setContentsMargins(0, 0, 0, 0)
        self.logo_icon_label = QLabel("✨", self.logo_widget)
        self.logo_icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.logo_icon_label.setStyleSheet("font-size: 24px; color: white;")
        logo_layout.addWidget(self.logo_icon_label)

        # Drop shadow for logo
        logo_shadow = QGraphicsDropShadowEffect(self)
        logo_shadow.setBlurRadius(20)
        logo_shadow.setColor(QColor(56, 189, 248, 160))
        logo_shadow.setOffset(0, 4)
        self.logo_widget.setGraphicsEffect(logo_shadow)

        self.stacked_layout.addWidget(self.logo_widget)

        # ================= VIEW 1: EXPANDED CHAT WINDOW =================
        self.chat_widget = QFrame(self)
        self.chat_widget.setObjectName("chatFrame")
        self.chat_widget.setStyleSheet("""
            QFrame#chatFrame {
                background: rgba(11, 17, 32, 0.96);
                border: 2px solid rgba(56, 189, 248, 0.6);
                border-radius: 18px;
            }
        """)

        chat_shadow = QGraphicsDropShadowEffect(self)
        chat_shadow.setBlurRadius(25)
        chat_shadow.setColor(QColor(0, 0, 0, 220))
        chat_shadow.setOffset(0, 8)
        self.chat_widget.setGraphicsEffect(chat_shadow)

        chat_layout = QVBoxLayout(self.chat_widget)
        chat_layout.setContentsMargins(14, 12, 14, 12)
        chat_layout.setSpacing(8)

        # Top Header Bar
        header_layout = QHBoxLayout()
        header_layout.setSpacing(6)

        header_icon = QLabel("✨", self.chat_widget)
        header_icon.setStyleSheet("font-size: 16px;")

        self.title_label = QLabel("GOLU AI", self.chat_widget)
        self.title_label.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        self.title_label.setStyleSheet("color: #38bdf8; letter-spacing: 1.5px;")

        self.badge_label = QLabel("READY", self.chat_widget)
        self.badge_label.setStyleSheet("""
            background: rgba(56, 189, 248, 0.2);
            color: #38bdf8;
            font-size: 9px;
            font-weight: bold;
            padding: 2px 6px;
            border-radius: 8px;
            border: 1px solid rgba(56, 189, 248, 0.4);
        """)

        header_layout.addWidget(header_icon)
        header_layout.addWidget(self.title_label)
        header_layout.addWidget(self.badge_label)
        header_layout.addStretch()

        # Dashboard Button
        btn_dash = QPushButton("📊", self.chat_widget)
        btn_dash.setToolTip("Open Web Dashboard")
        btn_dash.setStyleSheet("""
            QPushButton {
                background: rgba(56, 189, 248, 0.15);
                color: #38bdf8;
                border: 1px solid rgba(56, 189, 248, 0.3);
                border-radius: 6px;
                padding: 2px 6px;
                font-size: 12px;
            }
            QPushButton:hover { background: rgba(56, 189, 248, 0.35); }
        """)
        btn_dash.clicked.connect(lambda: webbrowser.open("http://127.0.0.1:8000/dashboard"))
        header_layout.addWidget(btn_dash)

        # Minimize to Logo Button
        btn_min = QPushButton("🗕", self.chat_widget)
        btn_min.setToolTip("Minimize to Golu Logo")
        btn_min.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #94a3b8;
                border: none;
                font-size: 13px;
                padding: 2px 4px;
            }
            QPushButton:hover { color: #38bdf8; }
        """)
        btn_min.clicked.connect(self.collapse_to_logo)
        header_layout.addWidget(btn_min)

        # Close Button
        btn_close = QPushButton("✕", self.chat_widget)
        btn_close.setToolTip("Hide Golu")
        btn_close.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #94a3b8;
                border: none;
                font-size: 13px;
                padding: 2px 4px;
            }
            QPushButton:hover { color: #f87171; }
        """)
        btn_close.clicked.connect(self.hide)
        header_layout.addWidget(btn_close)

        chat_layout.addLayout(header_layout)

        # Message Scroll Area
        self.scroll_area = QScrollArea(self.chat_widget)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("""
            QScrollArea {
                background: transparent;
                border: none;
            }
            QScrollBar:vertical {
                width: 6px;
                background: transparent;
            }
            QScrollBar::handle:vertical {
                background: rgba(148, 163, 184, 0.3);
                border-radius: 3px;
            }
        """)

        self.messages_container = QWidget()
        self.messages_container.setStyleSheet("background: transparent;")
        self.messages_layout = QVBoxLayout(self.messages_container)
        self.messages_layout.setContentsMargins(2, 2, 2, 2)
        self.messages_layout.setSpacing(8)
        self.messages_layout.addStretch()

        self.scroll_area.setWidget(self.messages_container)
        chat_layout.addWidget(self.scroll_area)

        # Add initial greeting message
        self.add_message_bubble("Namaste! Main Golu hoon. You can chat here or speak anytime!", is_user=False, source="GOLU")

        # Bottom Input & Action Bar
        bottom_bar = QHBoxLayout()
        bottom_bar.setSpacing(6)

        # Text input box for writing and chatting
        self.text_input = QLineEdit(self.chat_widget)
        self.text_input.setPlaceholderText("Type a message or question...")
        self.text_input.setStyleSheet("""
            QLineEdit {
                background: rgba(15, 23, 42, 0.8);
                color: #f8fafc;
                border: 1px solid rgba(56, 189, 248, 0.35);
                border-radius: 10px;
                padding: 6px 10px;
                font-size: 12px;
            }
            QLineEdit:focus {
                border: 1px solid #38bdf8;
                background: rgba(15, 23, 42, 0.95);
            }
        """)
        self.text_input.returnPressed.connect(self._handle_text_send)
        bottom_bar.addWidget(self.text_input)

        # Send Button
        btn_send = QPushButton("➤", self.chat_widget)
        btn_send.setToolTip("Send Message (Enter)")
        btn_send.setStyleSheet("""
            QPushButton {
                background: #0284c7;
                color: white;
                border: none;
                border-radius: 10px;
                padding: 6px 10px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:hover { background: #0369a1; }
        """)
        btn_send.clicked.connect(self._handle_text_send)
        bottom_bar.addWidget(btn_send)

        # Mic Button
        self.btn_mic = QPushButton("🎤", self.chat_widget)
        self.btn_mic.setToolTip("Speak to Golu (Ctrl+Alt+A)")
        self.btn_mic.setStyleSheet("""
            QPushButton {
                background: rgba(56, 189, 248, 0.2);
                color: #38bdf8;
                border: 1px solid rgba(56, 189, 248, 0.4);
                border-radius: 10px;
                padding: 6px 10px;
                font-size: 13px;
            }
            QPushButton:hover {
                background: rgba(56, 189, 248, 0.4);
                color: white;
            }
        """)
        self.btn_mic.clicked.connect(self._trigger_voice)
        bottom_bar.addWidget(self.btn_mic)

        chat_layout.addLayout(bottom_bar)
        self.stacked_layout.addWidget(self.chat_widget)

    def _connect_signals(self):
        self.comm.show_signal.connect(self._on_show)
        self.comm.hide_signal.connect(self.hide)
        self.comm.expand_signal.connect(self.expand_to_chat)
        self.comm.collapse_signal.connect(self.collapse_to_logo)
        self.comm.listening_signal.connect(self._on_listening)
        self.comm.transcript_signal.connect(self._on_transcript)
        self.comm.answer_signal.connect(self._on_answer)
        self.comm.close_signal.connect(self.close)

    def expand_to_chat(self):
        """Expands from logo into the chat window."""
        self.is_expanded = True
        self.stacked_layout.setCurrentIndex(1)
        self.resize(380, 480)
        self.text_input.setFocus()

    def collapse_to_logo(self):
        """Collapses back into the small 64x64 floating logo."""
        self.is_expanded = False
        self.stacked_layout.setCurrentIndex(0)
        self.resize(72, 72)

    def add_message_bubble(self, text: str, is_user: bool, source: str = ""):
        """Adds a modern styled message bubble into the chat area."""
        bubble_frame = QFrame(self.messages_container)
        bubble_layout = QVBoxLayout(bubble_frame)
        bubble_layout.setContentsMargins(10, 8, 10, 8)
        bubble_layout.setSpacing(3)

        if is_user:
            bubble_frame.setStyleSheet("""
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0284c7, stop:1 #0ea5e9);
                border-radius: 12px;
                border-bottom-right-radius: 2px;
            """)
            msg_label = QLabel(text, bubble_frame)
            msg_label.setStyleSheet("color: #ffffff; font-size: 12px;")
            msg_label.setWordWrap(True)
            bubble_layout.addWidget(msg_label)

            row = QHBoxLayout()
            row.addStretch()
            row.addWidget(bubble_frame)
            self.messages_layout.addLayout(row)
        else:
            bubble_frame.setStyleSheet("""
                background: rgba(30, 41, 59, 0.75);
                border: 1px solid rgba(56, 189, 248, 0.25);
                border-radius: 12px;
                border-bottom-left-radius: 2px;
            """)
            if source:
                src_label = QLabel(f"• {source.upper()}", bubble_frame)
                src_label.setStyleSheet("color: #38bdf8; font-size: 9px; font-weight: bold;")
                bubble_layout.addWidget(src_label)

            msg_label = QLabel(text, bubble_frame)
            msg_label.setStyleSheet("color: #f1f5f9; font-size: 12px;")
            msg_label.setWordWrap(True)
            bubble_layout.addWidget(msg_label)

            row = QHBoxLayout()
            row.addWidget(bubble_frame)
            row.addStretch()
            self.messages_layout.addLayout(row)

        # Auto-scroll to bottom
        QTimer.singleShot(50, lambda: self.scroll_area.verticalScrollBar().setValue(
            self.scroll_area.verticalScrollBar().maximum()
        ))

    def _handle_text_send(self):
        """Dispatches typed message to Assistant in background."""
        text = self.text_input.text().strip()
        if not text:
            return
        self.text_input.clear()
        self.add_message_bubble(text, is_user=True)
        self.badge_label.setText("THINKING")

        def worker():
            res = assistant.ask(text, allow_web_search=True)
            ans = res.get("answer", "")
            src = res.get("source", "brain")
            # Update chat
            self.comm.answer_signal.emit(ans, src)
            # Speak with natural Indian neural voice
            voice_engine.speak(ans)

        threading.Thread(target=worker, daemon=True).start()

    def _trigger_voice(self):
        """Triggers live voice recording."""
        try:
            from backend.state_machine import state_machine
            state_machine.on_hotkey_assistant()
        except Exception as e:
            logger.error("Error triggering mic: %s", e)

    def _on_show(self):
        self.show()
        self.raise_()
        self.activateWindow()

    def _on_listening(self, msg: str):
        self._is_listening = True
        self.expand_to_chat()
        self.show()
        self.badge_label.setText("LISTENING")
        self.badge_label.setStyleSheet("""
            background: rgba(234, 179, 8, 0.2);
            color: #facc15;
            font-size: 9px;
            font-weight: bold;
            padding: 2px 6px;
            border-radius: 8px;
            border: 1px solid rgba(234, 179, 8, 0.4);
        """)

    def _on_transcript(self, text: str):
        self.expand_to_chat()
        self.show()
        self.add_message_bubble(text, is_user=True)
        self.badge_label.setText("THINKING")
        self.badge_label.setStyleSheet("""
            background: rgba(192, 132, 252, 0.2);
            color: #c084fc;
            font-size: 9px;
            font-weight: bold;
            padding: 2px 6px;
            border-radius: 8px;
            border: 1px solid rgba(192, 132, 252, 0.4);
        """)

    def _on_answer(self, answer: str, source: str):
        self._is_listening = False
        self.expand_to_chat()
        self.show()
        self.badge_label.setText("ANSWERED")
        self.badge_label.setStyleSheet("""
            background: rgba(52, 211, 153, 0.2);
            color: #34d399;
            font-size: 9px;
            font-weight: bold;
            padding: 2px 6px;
            border-radius: 8px;
            border: 1px solid rgba(52, 211, 153, 0.4);
        """)
        self.add_message_bubble(answer, is_user=False, source=source)

    def _animate_pulse(self):
        """Pulsates the glowing border when listening or idle."""
        self._pulse_step = (self._pulse_step + 1) % 40
        if not self.is_expanded:
            # Pulsing floating logo
            alpha = int(140 + 100 * (self._pulse_step / 40.0 if self._pulse_step < 20 else (40 - self._pulse_step) / 20.0))
            self.logo_widget.setStyleSheet(f"""
                QFrame#logoFrame {{
                    background: qradialgradient(cx:0.5, cy:0.5, radius:0.5, fx:0.3, fy:0.3, stop:0 #38bdf8, stop:0.8 #0284c7, stop:1 #0f172a);
                    border: 2px solid rgba(56, 189, 248, {alpha / 255.0:.2f});
                    border-radius: 32px;
                }}
            """)

    # Click on logo expands into chat window; drag moves the widget anywhere
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self._press_pos = event.globalPosition().toPoint()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton and self._drag_pos is not None:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and getattr(self, "_press_pos", None) is not None:
            distance = (event.globalPosition().toPoint() - self._press_pos).manhattanLength()
            if distance < 8 and not self.is_expanded:
                self.expand_to_chat()
        self._drag_pos = None
        self._press_pos = None


def launch_siri_hud(communicator: Optional[SiriHUDCommunicator] = None) -> FloatingSiriHUD:
    hud = FloatingSiriHUD(communicator)
    hud.show()
    return hud


if __name__ == "__main__":
    app = QApplication(sys.argv)
    hud = launch_siri_hud()
    sys.exit(app.exec())
