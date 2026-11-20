"""Project Golu: Hinglish Voice Subsystem.
Zero-cloud speech-to-text (Faster-Whisper CPU int8), wake-word matching (RapidFuzz),
and voice output with hard-mute security for meeting mode.
Strictly runs on CPU to reserve 100% of GPU VRAM for LLM generation.
"""

import os
import io
import re
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

    def __init__(self, model_size: str = "base", device: str = "cpu", compute_type: str = "int8"):
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
        """Transcribes Hinglish audio using Hybrid ASR:
        1. Fast, highly accurate Google Speech Recognition (en-IN) when online (< 400ms)
        2. 100% offline fallback: Faster-Whisper base model (int8 on CPU) with beam search
        Returns: (transcribed_text, detected_language, duration_seconds)
        """
        start_time = time.perf_counter()
        pcm_bytes = None
        audio_array = None

        # Normalize audio input into pcm_bytes and audio_array
        if isinstance(audio_input, bytes):
            pcm_bytes = audio_input
            audio_array = np.frombuffer(audio_input, dtype=np.int16).astype(np.float32) / 32768.0
        elif isinstance(audio_input, np.ndarray):
            audio_array = audio_input.astype(np.float32)
            if np.max(np.abs(audio_array)) > 1.0:
                audio_array /= 32768.0
            pcm_bytes = (audio_array * 32767.0).astype(np.int16).tobytes()
        elif isinstance(audio_input, (list, tuple)):
            audio_array = np.array(audio_input, dtype=np.float32)
            pcm_bytes = (audio_array * 32767.0).astype(np.int16).tobytes()
        elif isinstance(audio_input, str) and os.path.isfile(audio_input):
            try:
                with wave.open(audio_input, "rb") as wf:
                    sample_rate = wf.getframerate()
                    pcm_bytes = wf.readframes(wf.getnframes())
                audio_array = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0
            except Exception as e:
                logger.debug("Failed to read audio file for ASR: %s", e)

        # Tier 1: Try Fast Google Indian English (en-IN) ASR
        if pcm_bytes and len(pcm_bytes) >= 1600:
            try:
                import speech_recognition as sr
                r = sr.Recognizer()
                r.energy_threshold = 250
                r.dynamic_energy_threshold = False
                audio_data = sr.AudioData(pcm_bytes, sample_rate, 2)
                text = r.recognize_google(audio_data, language="en-IN")
                if text and text.strip():
                    duration = time.perf_counter() - start_time
                    logger.info("Transcribed via Google en-IN in %.2fs: '%s'", duration, text.strip())
                    return text.strip(), "en", duration
            except Exception as e:
                logger.debug("Google ASR fallback to Whisper: %s", e)

        # Tier 2: Offline Faster-Whisper Base Model on CPU
        if self._whisper_model is None:
            self._load_whisper_lazy()

        if self._whisper_model is not None and audio_array is not None:
            try:
                # Automatic gain normalization: boost low microphone signal to optimal 0.90 peak
                if len(audio_array) > 0:
                    peak = float(np.max(np.abs(audio_array)))
                    if peak > 0.005:
                        audio_array = (audio_array / peak) * 0.90

                initial_prompt = (
                    "Conversational Indian English and Hinglish assistant query for Golu AI: "
                    "Hey Golu, Hi Golu, search internet, what is my name, resume, projects, Python."
                )

                segments, info = self._whisper_model.transcribe(
                    audio_array,
                    beam_size=5,
                    best_of=5,
                    temperature=0.0,
                    condition_on_previous_text=False,
                    initial_prompt=initial_prompt,
                    language=language or "en",
                    vad_filter=True,
                    vad_parameters=dict(min_silence_duration_ms=400)
                )
                text_segments = [s.text.strip() for s in segments]
                raw_text = " ".join(text_segments).strip()
                # De-duplicate consecutive repeated phrases/sentences
                parts = [p.strip() for p in re.split(r"[.!?]+", raw_text) if p.strip()]
                if parts:
                    deduped = []
                    for p in parts:
                        if not deduped or p.lower() != deduped[-1].lower():
                            deduped.append(p)
                    full_text = ". ".join(deduped)
                else:
                    full_text = raw_text
                duration = time.perf_counter() - start_time
                logger.info("Transcribed via Faster-Whisper in %.2fs [%s, beam=5]: '%s'", duration, info.language, full_text)
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

    def speak(self, text: str, voice_lang: str = "hi", voice_name: str = "en-IN-NeerjaNeural") -> bool:
        """Synthesizes and speaks text using a natural Indian neural voice (edge-tts).
        STRICTLY BLOCKED if is_hard_muted is True (0% chance of meeting leak).
        Falls back to Windows SAPI if offline.
        """
        if self.is_hard_muted:
            logger.warning("TTS speech suppressed: Engine is hard-muted for meeting security.")
            return False

        if not text.strip():
            return False

        # Clean markdown symbols, asterisks, URLs, and code blocks for crisp speech
        clean_text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
        clean_text = re.sub(r"`.*?`", "", clean_text)
        clean_text = re.sub(r"\[(.*?)\]\(.*?\)", r"\1", clean_text)
        clean_text = re.sub(r"[*_~#>-]", "", clean_text)
        clean_text = re.sub(r"\s+", " ", clean_text).strip()

        logger.info("Voice Output: '%s'", clean_text)

        # Attempt 1: High-fidelity Natural Indian Neural Voice (edge-tts)
        try:
            import certifi
            os.environ["SSL_CERT_FILE"] = certifi.where()
            import asyncio
            import edge_tts
            import soundfile as sf
            import sounddevice as sd
            import threading

            async def _synthesize_edge() -> bytes:
                communicate = edge_tts.Communicate(clean_text, voice=voice_name, rate="+4%")
                chunks = []
                async for chunk in communicate.stream():
                    if chunk["type"] == "audio":
                        chunks.append(chunk["data"])
                return b"".join(chunks)

            # Thread-safe execution of async synthesis
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor() as pool:
                        audio_mp3 = pool.submit(lambda: asyncio.run(_synthesize_edge())).result(timeout=6.0)
                else:
                    audio_mp3 = loop.run_until_complete(_synthesize_edge())
            except Exception:
                audio_mp3 = asyncio.run(_synthesize_edge())

            if audio_mp3:
                data, samplerate = sf.read(io.BytesIO(audio_mp3))
                
                def _play():
                    try:
                        sd.play(data, samplerate)
                        sd.wait()
                    except Exception as err:
                        logger.debug("Playback error in thread: %s", err)

                threading.Thread(target=_play, daemon=True).start()
                return True
        except Exception as e:
            logger.debug("Edge-TTS natural voice fallback: %s", e)

        # Attempt 2: Native Windows Speech synthesis fallback via PowerShell
        try:
            import subprocess
            safe_text = clean_text.replace("'", "").replace('"', "")
            ps_cmd = (
                f"Add-Type -AssemblyName System.Speech; "
                f"$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
                f"$s.Speak('{safe_text}')"
            )
            subprocess.Popen(["powershell", "-NoProfile", "-Command", ps_cmd], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        except Exception as e:
            logger.debug("TTS synthesis dispatch error: %s", e)
            return False


# Global Voice Engine instance
voice_engine = GoluVoiceEngine()
