"""Project Golu: Finite State Machine (FSM) & Global Hotkey Manager.
Enforces mutual exclusivity between Voice Assistant and Meeting Co-Pilot modes,
preventing audio feedback loops, GPU contention, and meeting audio leaks.
Supported Hotkeys:
- [Ctrl+Alt+A] : MODE_ASSISTANT (Opens mic, plays chime, listens for query/wake word)
- [Ctrl+Alt+M] : MODE_MEETING (Hard-mutes TTS, activates WASAPI loopback, shows HUD)
- [Ctrl+Alt+H] : MODE_HIDE_HUD (Toggle screen visibility)
- [Ctrl+Alt+X] : MODE_KILL (Emergency kill switch < 50ms)
"""

import time
import logging
from enum import Enum
from typing import Callable, Optional, List

from backend.audio.golu_voice import voice_engine
from backend.audio.loopback_listener import loopback_listener
from backend.audio.mic_listener import mic_listener

logger = logging.getLogger("golu.fsm")


class GoluMode(str, Enum):
    IDLE = "IDLE"
    ASSISTANT = "MODE_ASSISTANT"
    MEETING = "MODE_MEETING"
    KILL = "MODE_KILL"


class FiniteStateMachine:
    """Strictly mutually exclusive state manager for Project Golu."""

    def __init__(self):
        self.current_mode: GoluMode = GoluMode.IDLE
        self.hud_visible: bool = False
        self._hud_communicator = None
        self._hotkey_listener = None
        self._state_callbacks: List[Callable[[GoluMode], None]] = []

    def set_hud_communicator(self, communicator):
        """Attaches the Qt HUD communicator."""
        self._hud_communicator = communicator

    def register_state_callback(self, callback: Callable[[GoluMode], None]):
        """Registers a listener for mode changes."""
        self._state_callbacks.append(callback)

    def transition_to(self, target_mode: GoluMode) -> GoluMode:
        """Executes atomic state transition enforcing non-negotiable rules."""
        logger.info("Transitioning from %s -> %s", self.current_mode, target_mode)

        if target_mode == GoluMode.ASSISTANT:
            # Rule 1: Meeting loopback strictly OFF
            loopback_listener.stop()
            # Rule 2: TTS unmuted
            voice_engine.set_hard_mute(False)
            # Rule 3: Start Microphone Listener
            mic_listener.start()
            # Rule 4: Hide HUD
            if self._hud_communicator:
                self._hud_communicator.wipe_signal.emit()
            self.hud_visible = False
            self.current_mode = GoluMode.ASSISTANT
            logger.info("MODE_ASSISTANT Active: Voice mic on, TTS unmuted, WASAPI loopback off.")

        elif target_mode == GoluMode.MEETING:
            # Rule 1: Hard-mute TTS (0% chance of audio leak into call)
            voice_engine.set_hard_mute(True)
            # Rule 2: Stop microphone assistant listener
            mic_listener.stop()
            # Rule 3: Start WASAPI loopback capture
            loopback_listener.start()
            # Rule 4: Show Stealth HUD
            if self._hud_communicator:
                self._hud_communicator.toggle_signal.emit()
            self.hud_visible = True
            self.current_mode = GoluMode.MEETING
            logger.info("MODE_MEETING Active: TTS hard-muted (0% leak), WASAPI loopback active, Stealth HUD on.")

        elif target_mode == GoluMode.KILL:
            t0 = time.perf_counter()
            # Emergency Shutdown in < 50ms: release all audio handles
            mic_listener.stop()
            loopback_listener.stop()
            voice_engine.set_hard_mute(True)
            if self._hud_communicator:
                self._hud_communicator.wipe_signal.emit()
            self.hud_visible = False
            self.current_mode = GoluMode.KILL
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            logger.warning("MODE_KILL Executed: Emergency shutdown in %.2fms (Target < 50ms).", elapsed_ms)

        # Notify callbacks
        for cb in self._state_callbacks:
            try:
                cb(self.current_mode)
            except Exception as e:
                logger.error("State callback error: %s", e)

        return self.current_mode

    def on_hotkey_assistant(self):
        """[Ctrl+Alt+A]: Activates Assistant Mode, plays instant feedback chime, and listens for query."""
        logger.info("Hotkey [Ctrl+Alt+A] detected.")
        self.transition_to(GoluMode.ASSISTANT)
        mic_listener.trigger_manual_listen()

    def on_hotkey_meeting(self):
        """[Ctrl+Alt+M]: Activates Stealth Meeting Mode."""
        logger.info("Hotkey [Ctrl+Alt+M] detected.")
        self.transition_to(GoluMode.MEETING)

    def on_hotkey_kill(self):
        """[Ctrl+Alt+X]: Emergency kill switch."""
        logger.info("Hotkey [Ctrl+Alt+X] detected.")
        self.transition_to(GoluMode.KILL)

    def toggle_hud(self):
        """[Ctrl+Alt+H]: Instantly toggles HUD visibility on physical monitor."""
        if self._hud_communicator:
            self._hud_communicator.toggle_signal.emit()
            self.hud_visible = not self.hud_visible
            logger.info("HUD Visibility toggled to: %s", self.hud_visible)

    def start_hotkey_listener(self):
        """Starts background global hotkey listener via pynput."""
        try:
            from pynput import keyboard

            hotkeys = {
                '<ctrl>+<alt>+a': self.on_hotkey_assistant,
                '<ctrl>+<alt>+m': self.on_hotkey_meeting,
                '<ctrl>+<alt>+h': self.toggle_hud,
                '<ctrl>+<alt>+x': self.on_hotkey_kill,
            }

            self._hotkey_listener = keyboard.GlobalHotKeys(hotkeys)
            self._hotkey_listener.daemon = True
            self._hotkey_listener.start()
            logger.info("Global hotkeys initialized: [Ctrl+Alt+A/M/H/X].")
        except Exception as e:
            logger.warning("Failed to start global hotkey listener: %s (Headless / test environment safe).", e)

    def stop_hotkey_listener(self):
        if self._hotkey_listener:
            try:
                self._hotkey_listener.stop()
            except Exception as e:
                logger.debug("Error stopping hotkey listener: %s", e)
            finally:
                self._hotkey_listener = None


# Global State Machine instance
state_machine = FiniteStateMachine()
