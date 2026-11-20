"""Project Golu: Real-Time Microphone Listener & Voice Assistant Worker.
Listens to the local microphone, performs energy-based VAD filtering (< 2% CPU idle),
detects wake words ('Hey Golu' / 'Hi Golu'), handles instant manual triggers via [Ctrl+Alt+A],
and dispatches queries to Golu's Unified Assistant (Vault + RAG + Internet Search + Local LLM).
"""

import time
import queue
import logging
import threading
from typing import Optional, Callable
import numpy as np
import sounddevice as sd

from backend.audio.golu_voice import voice_engine
from backend.assistant import assistant

logger = logging.getLogger("golu.audio.mic")

SAMPLE_RATE = 16000
CHANNELS = 1
BLOCK_SIZE = 1600  # 100ms blocks at 16kHz
SILENCE_THRESHOLD_RMS = 120.0  # RMS energy threshold for speech detection
SILENCE_TIMEOUT_BLOCKS = 8     # ~800ms of consecutive silence ends utterance
MAX_UTTERANCE_BLOCKS = 80      # ~8.0 seconds max recording


class MicrophoneListener:
    """Continuous low-latency microphone listener for Project Golu."""

    def __init__(self):
        self._stream: Optional[sd.InputStream] = None
        self._running: bool = False
        self._thread: Optional[threading.Thread] = None
        self._audio_queue: queue.Queue = queue.Queue()
        self._manual_listen: bool = False
        self._lock = threading.Lock()
        self._on_query_callback: Optional[Callable[[str, str], None]] = None

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

        logger.info("Manual voice query triggered via shortcut [Ctrl+Alt+A].")
        # Play instant acknowledgement chime / clip
        voice_engine.play_reaction_clip("ack_haan_bhai.wav")

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

        logger.info("Microphone listener worker active. Waiting for 'Hey Golu' or [Ctrl+Alt+A]...")

        while self._running:
            try:
                chunk = self._audio_queue.get(timeout=0.2)
            except queue.Empty:
                continue

            # If hard-muted (in Meeting mode), discard audio
            if voice_engine.is_hard_muted:
                time.sleep(0.1)
                continue

            rms = voice_engine.compute_vad_rms(chunk)
            is_above_threshold = (rms >= SILENCE_THRESHOLD_RMS)

            with self._lock:
                manual_active = self._manual_listen

            if is_above_threshold or manual_active:
                if not is_speech_active:
                    is_speech_active = True
                    silence_count = 0
                    speech_buffer = [chunk]
                else:
                    speech_buffer.append(chunk)
                    silence_count = 0

                # Utterance length safety cap
                if len(speech_buffer) >= MAX_UTTERANCE_BLOCKS:
                    self._process_utterance(b"".join(speech_buffer), manual_active)
                    speech_buffer = []
                    is_speech_active = False
                    silence_count = 0
                    with self._lock:
                        self._manual_listen = False
            elif is_speech_active:
                speech_buffer.append(chunk)
                silence_count += 1
                if silence_count >= SILENCE_TIMEOUT_BLOCKS:
                    # Utterance finished
                    self._process_utterance(b"".join(speech_buffer), manual_active)
                    speech_buffer = []
                    is_speech_active = False
                    silence_count = 0
                    with self._lock:
                        self._manual_listen = False

    def _process_utterance(self, audio_bytes: bytes, was_manual: bool):
        """Transcribes speech and routes to Assistant."""
        if len(audio_bytes) < BLOCK_SIZE * 3:
            # Too short (< 300ms), likely click or transient noise
            return

        logger.info("Transcribing captured speech (%d bytes)...", len(audio_bytes))
        transcript, lang, dur = voice_engine.transcribe(audio_bytes)
        transcript = transcript.strip()

        if not transcript:
            return

        logger.info("Captured voice transcript: '%s'", transcript)

        query = ""
        should_process = False

        if was_manual:
            # User explicitly pressed shortcut, treat entire transcript as query
            should_process = True
            query = transcript
        else:
            # Check for wake word ('Hey Golu', 'Hi Golu', etc.)
            is_wake, remaining = voice_engine.detect_wake_word(transcript)
            if is_wake:
                should_process = True
                voice_engine.play_reaction_clip("ack_haan_bhai.wav")
                if remaining:
                    query = remaining
                else:
                    # Spoke wake word only, prime manual listen for follow-up
                    with self._lock:
                        self._manual_listen = True
                    return

        if should_process and query:
            logger.info("Processing voice query: '%s'", query)
            res = assistant.ask(query, allow_web_search=True)
            answer = res.get("answer", "")
            source = res.get("source", "unknown")
            logger.info("Voice Assistant answer [%s]: '%s'", source, answer)

            if self._on_query_callback:
                try:
                    self._on_query_callback(query, answer)
                except Exception as e:
                    logger.debug("Error in query callback: %s", e)

            # Speak answer back to user
            voice_engine.speak(answer)


# Global microphone listener instance
mic_listener = MicrophoneListener()


if __name__ == "__main__":
    import sys
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
