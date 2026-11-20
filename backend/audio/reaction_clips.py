"""Project Golu: Pre-rendered Sub-100ms Reaction Audio Clips.
Generates and caches instant acknowledgement audio clips for natural conversation:
"Haan bhai, bolo?", "Haan ji", "Sun raha hoon", "Ek second..."
"""

import os
import wave
import struct
import math
import logging

logger = logging.getLogger("golu.audio.reactions")

CLIPS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data", "audio_clips"))


def ensure_audio_clips():
    """Generates synthetic notification/speech tones or loads cached audio clips."""
    os.makedirs(CLIPS_DIR, exist_ok=True)
    
    clip_files = {
        "ack_haan_bhai.wav": (440.0, 0.25, "Haan bhai, bolo?"),
        "ack_sun_raha_hoon.wav": (523.25, 0.2, "Sun raha hoon"),
        "ack_ek_second.wav": (349.23, 0.2, "Ek second..."),
        "alert_meeting.wav": (659.25, 0.15, "Meeting Mode Active"),
        "alert_kill.wav": (220.0, 0.1, "Emergency Kill Triggered")
    }
    
    for filename, (freq, duration, label) in clip_files.items():
        filepath = os.path.join(CLIPS_DIR, filename)
        if not os.path.exists(filepath):
            _generate_tone_wav(filepath, freq, duration)
            logger.info("Generated reaction audio clip: %s (%s)", filename, label)


def _generate_tone_wav(filepath: str, freq: float, duration: float, sample_rate: int = 16000):
    """Generates a pleasant chime WAV file as offline sub-100ms instant reaction."""
    num_samples = int(sample_rate * duration)
    with wave.open(filepath, "w") as wav_file:
        wav_file.setnchannels(1)  # Mono
        wav_file.setsampwidth(2)  # 16-bit
        wav_file.setframerate(sample_rate)
        
        frames = []
        for i in range(num_samples):
            t = float(i) / sample_rate
            # Smooth envelope (attack + exponential decay)
            envelope = math.exp(-3.0 * t / duration) * min(1.0, t / 0.02)
            # Harmonic richness
            val = envelope * (
                0.7 * math.sin(2.0 * math.pi * freq * t) +
                0.3 * math.sin(2.0 * math.pi * freq * 2.0 * t)
            )
            sample = int(val * 32767.0 * 0.5)
            frames.append(struct.pack("<h", max(-32767, min(32767, sample))))
            
        wav_file.writeframes(b"".join(frames))


def get_reaction_clip(name: str = "ack_haan_bhai.wav") -> str:
    """Returns absolute path to requested pre-rendered audio clip."""
    ensure_audio_clips()
    filepath = os.path.join(CLIPS_DIR, name)
    if not os.path.exists(filepath):
        _generate_tone_wav(filepath, 440.0, 0.2)
    return filepath


if __name__ == "__main__":
    ensure_audio_clips()
    print("Reaction audio clips initialized at:", CLIPS_DIR)
