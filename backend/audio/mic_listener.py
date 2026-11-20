"""Project Golu: Real-Time Microphone Listener & Voice Assistant Worker.
Features:
- Circular pre-roll buffer (300ms) to prevent clipping initial syllables
- Dynamic adaptive RMS noise floor calibration
- Whisper decoding with beam search and Hinglish context conditioning
- Bridge to Floating Siri HUD (stealth_hud/siri_hud.py)
- Hands-free wake word ('Hey Golu') and manual shortcut trigger [Ctrl+Alt+A]
"""

import time
import queue
import logging
import threading
from collections import deque
from typing import Optional, Callable
import numpy as np
import sounddevice as sd

from backend.audio.golu_voice import voice_engine
from backend.assistant import assistant
from stealth_hud.siri_hud import siri_communicator

logger = logging.getLogger("golu.audio.mic")

SAMPLE_RATE = 16000
CHANNELS = 1
BLOCK_SIZE = 1600          # 100ms blocks at 16kHz
DEFAULT_THRESHOLD_RMS = 80.0
SILENCE_TIMEOUT_BLOCKS = 8 # ~800ms of consecutive silence ends utterance
MAX_UTTERANCE_BLOCKS = 90  # ~9.0 seconds max recording


class MicrophoneListener:
    """Continuous low-latency microphone listener for Project Golu."""

    def __init__(self):
        self._stream: Optional[sd.InputStream] = None
        self._running: bool = False
        self._thread: Optional[threading.Thread] = None
        self._audio_queue: queue.Queue = queue.Queue()
        self._manual_listen: bool = False
        self._manual_listen_start_time: float = 0.0
        self._lock = threading.Lock()
        self._on_query_callback: Optional[Callable[[str, str], None]] = None
        self.silence_threshold: float = DEFAULT_THRESHOLD_RMS

    def register_query_callback(self, cb: Callable[[str, str], None]):
        """Callback(query, answer) to notify HUD or other clients."""
        self._on_query_callback = cb

    def _audio_callback(self, indata, frames, time_info, status):
        """Low-level sounddevice audio callback."""
        if status:
            logger.debug("Audio stream status: %s", status)
        if self._running:
            self._audio_queue.put(bytes(indata))

    def trigger_manual_listen(self):
        """Called when [Ctrl+Alt+A] is pressed: gives immediate audio feedback and primes for query."""
        with self._lock:
            self._manual_listen = True
            self._manual_listen_start_time = time.perf_counter()

        logger.info("Manual voice query triggered via shortcut [Ctrl+Alt+A].")
        # Visual notification on Floating Siri HUD
        try:
            siri_communicator.listening_signal.emit("Haan bhai, bolo! Listening...")
        except Exception:
            pass

        # Play instant manly acknowledgement
        voice_engine.speak("Haan bhai, bolo!")

    def start(self):
        """Starts background microphone listening thread."""
        with self._lock:
            if self._running:
                return
            self._running = True

        # Clear queue
        while not self._audio_queue.empty():
            try:
                self._audio_queue.get_nowait()
            except queue.Empty:
                break

        try:
            self._stream = sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=CHANNELS,
                dtype="int16",
                blocksize=BLOCK_SIZE,
                callback=self._audio_callback
            )
            self._stream.start()
            self._thread = threading.Thread(target=self._worker_loop, daemon=True)
            self._thread.start()
            logger.info("MicrophoneListener started on default recording device.")
        except Exception as e:
            logger.error("Failed to start MicrophoneListener: %s", e)
            self._running = False

    def stop(self):
        """Stops background microphone listening thread and releases audio device handles."""
        with self._lock:
            if not self._running:
                return
            self._running = False
            self._manual_listen = False

        # Wake up worker thread immediately
        self._audio_queue.put(b"")

        if self._stream is not None:
            try:
                self._stream.abort()
                self._stream.close()
            except Exception as e:
                logger.debug("Error closing microphone stream: %s", e)
            finally:
                self._stream = None

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=0.2)
            self._thread = None

        logger.info("MicrophoneListener stopped and hardware handles released.")

    def _worker_loop(self):
        """Main processing loop: VAD filtering, wake word matching, and answering."""
        speech_buffer = []
        is_speech_active = False
        silence_count = 0
        pre_roll = deque(maxlen=3)  # 300ms pre-roll circular buffer to catch initial consonants
        noise_samples = []

        logger.info("Microphone listener worker active. Waiting for 'Hey Golu' or [Ctrl+Alt+A]...")

        while self._running:
            try:
                chunk = self._audio_queue.get(timeout=0.2)
            except queue.Empty:
                continue

            if not chunk:
                # Sentinel wake-up on shutdown
                continue

            # If hard-muted (in Meeting mode), discard audio
            if voice_engine.is_hard_muted:
                time.sleep(0.1)
                continue

            rms = voice_engine.compute_vad_rms(chunk)

            # Adaptive noise floor calibration for the first 5 blocks
            if len(noise_samples) < 5:
                noise_samples.append(rms)
                if len(noise_samples) == 5:
                    avg_noise = sum(noise_samples) / 5.0
                    self.silence_threshold = max(60.0, avg_noise * 1.8)
                    logger.info("Calibrated ambient mic noise floor: %.1f RMS (Threshold: %.1f RMS)", avg_noise, self.silence_threshold)

            with self._lock:
                manual_active = self._manual_listen
                # Auto-timeout conversational listen if user stays silent for > 15 seconds
                if manual_active and (time.perf_counter() - self._manual_listen_start_time > 15.0):
                    self._manual_listen = False
                    manual_active = False

            is_above_threshold = (rms >= self.silence_threshold)

            if is_above_threshold:
                if not is_speech_active:
                    is_speech_active = True
                    silence_count = 0
                    # Prepend pre-roll buffer to preserve attack transient of first word
                    speech_buffer = list(pre_roll) + [chunk]
                    try:
                        siri_communicator.listening_signal.emit("Listening to you...")
                    except Exception:
                        pass
                else:
                    speech_buffer.append(chunk)
                    silence_count = 0

                # Utterance length safety cap (~9s)
                if len(speech_buffer) >= MAX_UTTERANCE_BLOCKS:
                    try:
                        siri_communicator.transcript_signal.emit("Processing your speech...")
                    except Exception:
                        pass
                    self._process_utterance(b"".join(speech_buffer), manual_active)
                    speech_buffer = []
                    is_speech_active = False
                    silence_count = 0
                    with self._lock:
                        self._manual_listen = False
            elif is_speech_active:
                speech_buffer.append(chunk)
                silence_count += 1
                # 5 consecutive silent blocks (~500ms) ends the utterance fast!
                if silence_count >= 5:
                    try:
                        siri_communicator.transcript_signal.emit("Processing your speech...")
                    except Exception:
                        pass
                    self._process_utterance(b"".join(speech_buffer), manual_active)
                    speech_buffer = []
                    is_speech_active = False
                    silence_count = 0
                    with self._lock:
                        self._manual_listen = False
            else:
                pre_roll.append(chunk)

    def _process_utterance(self, audio_bytes: bytes, was_manual: bool):
        """Transcribes speech and routes to Assistant."""
        if len(audio_bytes) < BLOCK_SIZE * 3:
            # Too short (< 300ms), transient noise
            return

        logger.info("Processing captured speech (%d bytes)...", len(audio_bytes))
        transcript, lang, dur = voice_engine.transcribe(audio_bytes)
        transcript = transcript.strip()

        if not transcript:
            return

        logger.info("Captured voice transcript [%.2fs]: '%s'", dur, transcript)

        query = ""
        should_process = False

        is_wake, remaining = voice_engine.detect_wake_word(transcript)

        if was_manual:
            should_process = True
            # If user repeated wake word in conversational mode, strip it cleanly
            query = remaining if (is_wake and remaining) else transcript
        else:
            if is_wake:
                should_process = True
                if remaining:
                    query = remaining
                else:
                    # User greeted Golu without specific query
                    greeting = "Haan bhai, bolo!"
                    logger.info("Wake word detected. Responding: '%s'", greeting)
                    try:
                        siri_communicator.transcript_signal.emit(transcript)
                        siri_communicator.answer_signal.emit(greeting, "conversational")
                    except Exception:
                        pass
                    voice_engine.speak(greeting)
                    with self._lock:
                        self._manual_listen = True
                        self._manual_listen_start_time = time.perf_counter()
                    return

        if should_process and query:
            logger.info("Executing assistant query: '%s'", query)
            # Update Floating Siri HUD with transcript
            try:
                siri_communicator.transcript_signal.emit(query)
            except Exception:
                pass

            res = assistant.ask(query, allow_web_search=True)
            answer = res.get("answer", "")
            source = res.get("source", "unknown")
            logger.info("Assistant answer [%s]: '%s'", source, answer)

            # Update Floating Siri HUD with answer
            try:
                siri_communicator.answer_signal.emit(answer, source)
            except Exception:
                pass

            if self._on_query_callback:
                try:
                    self._on_query_callback(query, answer)
                except Exception as e:
                    logger.debug("Error in query callback: %s", e)

            # Speak answer back aloud to user
            voice_engine.speak(answer)

            # Re-arm conversational follow-up window for 15 seconds
            with self._lock:
                self._manual_listen = True
                self._manual_listen_start_time = time.perf_counter()


# Global microphone listener instance
mic_listener = MicrophoneListener()


if __name__ == "__main__":
    print("""
    ==================================================================
        PROJECT GOLU: LIVE VOICE ASSISTANT MIC TEST
    ==================================================================
      Say: 'Hey Golu, what is my full name?'
      Say: 'Hey Golu, search internet for quantum computing'
      Say: 'Hey Golu, what projects have I built?'
      
      Or press [Enter] here to simulate pressing [Ctrl + Alt + A]!
      Type 'q' and press [Enter] to exit.
    ==================================================================
    """)
    mic_listener.start()
    try:
        while True:
            line = input("Press [Enter] to trigger Golu listen (or 'q' to quit): ").strip()
            if line.lower() == 'q':
                break
            mic_listener.trigger_manual_listen()
            print("Listening for your voice... speak now!")
    except KeyboardInterrupt:
        pass
    finally:
        mic_listener.stop()
        print("Microphone test finished.")
