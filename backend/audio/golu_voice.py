"""Project Golu: Hinglish Voice Subsystem.
Zero-cloud speech-to-text (Faster-Whisper CPU int8), wake-word matching (RapidFuzz),
and voice output with hard-mute security for meeting mode.
Strictly runs on CPU to reserve 100% of GPU VRAM for LLM generation.
"""

import os
import io
import time
import wave
import struct
import math
import logging
from typing import Tuple, Optional, Union
import numpy as np
from rapidfuzz import fuzz

from backend.audio.reaction_clips import get_reaction_clip

logger = logging.getLogger("golu.audio.voice")

# Canonical wake word aliases
WAKE_WORDS = [
    "hi golu", "hey golu", "golu", "hai golu",
    "he golu", "hello golu", "oye golu", "suno golu"
]


class GoluVoiceEngine:
    """Zero-Cloud Hinglish Voice Interface Engine.
    Operates 100% on CPU, keeping GPU VRAM strictly isolated for LLM inference.
    """

    def __init__(self, model_size: str = "tiny", device: str = "cpu", compute_type: str = "int8"):
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self._whisper_model = None
        self.is_hard_muted: bool = False  # Strictly True in MODE_MEETING
        self._load_whisper_lazy()

    def _load_whisper_lazy(self):
        """Lazy loader for faster-whisper on CPU."""
        if self._whisper_model is None:
            try:
                import faster_whisper
                logger.info("Initializing Faster-Whisper (%s, %s, %s)...", self.model_size, self.device, self.compute_type)
                self._whisper_model = faster_whisper.WhisperModel(
                    self.model_size,
                    device=self.device,
                    compute_type=self.compute_type,
                    cpu_threads=4
                )
                logger.info("Faster-Whisper model initialized on CPU.")
            except Exception as e:
                logger.warning("Failed to initialize Faster-Whisper: %s. Using mock fallback if testing.", e)

    def set_hard_mute(self, muted: bool):
        """Hard-mutes all audio output. When True, zero sound can leave the speaker."""
        self.is_hard_muted = muted
        logger.info("Voice Engine Hard-Mute State: %s", "MUTED (0% leak)" if muted else "ACTIVE")

    @staticmethod
    def compute_vad_rms(pcm_bytes: bytes) -> float:
        """Calculates RMS audio energy to skip processing silence (< 2% CPU idle)."""
        if not pcm_bytes:
            return 0.0
        count = len(pcm_bytes) // 2
        if count == 0:
            return 0.0
        format_str = f"<{count}h"
        try:
            shorts = struct.unpack(format_str, pcm_bytes[:count * 2])
            sum_squares = sum(s * s for s in shorts)
            rms = math.sqrt(sum_squares / count)
            return rms
        except Exception:
            return 0.0

    def transcribe(
        self,
        audio_input: Union[str, np.ndarray, bytes],
        sample_rate: int = 16000,
        language: Optional[str] = None
    ) -> Tuple[str, str, float]:
        """Transcribes Hinglish audio using Faster-Whisper on CPU.
        Returns: (transcribed_text, detected_language, duration_seconds)
        """
        start_time = time.perf_counter()
        
        # If input is raw PCM bytes, convert to numpy float32
        if isinstance(audio_input, bytes):
            audio_array = np.frombuffer(audio_input, dtype=np.int16).astype(np.float32) / 32768.0
        elif isinstance(audio_input, np.ndarray):
            audio_array = audio_input.astype(np.float32)
            if np.max(np.abs(audio_array)) > 1.0:
                audio_array /= 32768.0
        else:
            # File path string
            audio_array = audio_input

        if self._whisper_model is None:
            self._load_whisper_lazy()

        if self._whisper_model is not None:
            try:
                segments, info = self._whisper_model.transcribe(
                    audio_array,
                    beam_size=1,
                    language=language,
                    vad_filter=True,
                    vad_parameters=dict(min_silence_duration_ms=500)
                )
                text_segments = [s.text.strip() for s in segments]
                full_text = " ".join(text_segments).strip()
                duration = time.perf_counter() - start_time
                logger.info("Transcribed in %.2fs [%s]: '%s'", duration, info.language, full_text)
                return full_text, info.language, duration
            except Exception as e:
                logger.error("Whisper transcription error: %s", e)
                return "", "en", time.perf_counter() - start_time

        return "", "en", 0.0

    def detect_wake_word(self, transcript: str) -> Tuple[bool, str]:
        """Checks if transcript contains the wake word ('Hi Golu' / 'Hey Golu') using token-bounded RapidFuzz.
        Returns: (is_wake_word, remaining_query)
        """
        clean_text = transcript.lower().strip()
        if not clean_text:
            return False, ""

        words = clean_text.split()
        for wake in WAKE_WORDS:
            wake_words = wake.split()
            n = len(wake_words)
            if len(words) >= n:
                candidate = " ".join(words[:n]).strip(" ,?!")
                if candidate == wake:
                    remaining = " ".join(words[n:]).strip(" ,?!")
                    return True, remaining
                if fuzz.ratio(candidate, wake) >= 82:
                    # Token-level verification: final word must match 'golu' with >= 75 score (rejects 'google', etc.)
                    last_token = words[n - 1].strip(" ,?!")
                    if fuzz.ratio(last_token, wake_words[-1]) >= 75:
                        remaining = " ".join(words[n:]).strip(" ,?!")
                        return True, remaining

        return False, clean_text

    def play_reaction_clip(self, clip_name: str = "ack_haan_bhai.wav") -> bool:
        """Plays sub-100ms reaction audio clip.
        STRICTLY BLOCKED if is_hard_muted is True.
        """
        if self.is_hard_muted:
            logger.warning("Playback blocked: Golu is in HARD-MUTE mode.")
            return False

        clip_path = get_reaction_clip(clip_name)
        if not os.path.exists(clip_path):
            return False

        try:
            import sounddevice as sd
            import soundfile as sf
            data, fs = sf.read(clip_path)
            sd.play(data, fs)
            return True
        except Exception as e:
            logger.debug("Playback error (sounddevice): %s", e)
            return False

    def speak(self, text: str, voice_lang: str = "hi") -> bool:
        """Synthesizes and speaks text.
        STRICTLY BLOCKED if is_hard_muted is True (0% chance of meeting leak).
        """
        if self.is_hard_muted:
            logger.warning("TTS speech suppressed: Engine is hard-muted for meeting security.")
            return False

        if not text.strip():
            return False

        logger.info("Voice Output: '%s'", text)
        
        # Native Windows Speech synthesis fallback via PowerShell
        try:
            import subprocess
            clean_text = text.replace("'", "").replace('"', "")
            ps_cmd = (
                f"Add-Type -AssemblyName System.Speech; "
                f"$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
                f"$s.Speak('{clean_text}')"
            )
            subprocess.Popen(["powershell", "-NoProfile", "-Command", ps_cmd], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        except Exception as e:
            logger.debug("TTS synthesis dispatch error: %s", e)
            return False


# Global Voice Engine instance
voice_engine = GoluVoiceEngine()
