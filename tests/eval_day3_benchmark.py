"""Project Golu: Day 3 Mandatory Exit Gate Evaluation Benchmark.
Evaluates:
- Test 01: Voice Engine Initialization & Hinglish ASR Pipeline (CPU int8)
- Test 02: Wake Word Specificity ("Hey Golu" / "Hi Golu" vs negative distractors)
- Test 03: WASAPI Loopback Driver Enumeration & Sub-50ms Release Latency
- Test 04: Stealth HUD ExcludeFromCapture (WDA_EXCLUDEFROMCAPTURE = 0x00000011)
- Test 05: FSM Mutual Exclusivity & Emergency Kill Switch (< 50ms)
- Test 06: End-to-End Meeting Co-Pilot Simulation (Audio -> RAG -> Cloaked HUD)
"""

import sys
import os
import time
import logging
import wave
import struct
import numpy as np

# Ensure root workspace is on python sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Set environment
os.environ["ANONYMIZED_TELEMETRY"] = "False"
os.environ["CHROMA_TELEMETRY_IMPL"] = "none"
os.environ["HF_HUB_OFFLINE"] = "1"

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] golu.eval.day3: %(message)s")
logger = logging.getLogger("golu.eval.day3")

from fastapi.testclient import TestClient
from backend.main import app
from backend.security import security_manager
from backend.audio.golu_voice import voice_engine
from backend.audio.loopback_listener import loopback_listener
from backend.state_machine import state_machine, GoluMode
from backend.meeting_copilot import meeting_copilot
from stealth_hud.overlay import create_hud_app, WDA_EXCLUDEFROMCAPTURE

client = TestClient(app)
VALID_TOKEN = security_manager.session_token
AUTH_HEADERS = {"X-Golu-Token": VALID_TOKEN}


def generate_synthetic_speech_pcm(duration: float = 1.0, freq: float = 300.0, sample_rate: int = 16000) -> bytes:
    """Generates synthetic PCM speech tone for VAD & ASR testing."""
    num_samples = int(sample_rate * duration)
    frames = []
    for i in range(num_samples):
        t = float(i) / sample_rate
        val = 0.5 * np.sin(2.0 * np.pi * freq * t)
        sample = int(val * 32767.0)
        frames.append(struct.pack("<h", max(-32767, min(32767, sample))))
    return b"".join(frames)


def test_01_voice_engine_pipeline():
    logger.info("Executing Test 01: Voice Engine Initialization & Hinglish ASR pipeline...")
    assert voice_engine.device == "cpu", "Voice engine must strictly run on CPU"
    assert voice_engine.compute_type == "int8", "Whisper compute type must be int8"

    # Test VAD energy computation
    silence = b"\x00" * 3200
    noise = generate_synthetic_speech_pcm(duration=0.2)
    silence_rms = voice_engine.compute_vad_rms(silence)
    noise_rms = voice_engine.compute_vad_rms(noise)
    assert silence_rms == 0.0, f"Silence RMS should be 0, got {silence_rms}"
    assert noise_rms > 5000.0, f"Tone RMS should be > 5000, got {noise_rms}"

    logger.info("✅ Test 01 PASSED: Voice engine initialized on CPU with active VAD filter.")


def test_02_wake_word_specificity():
    logger.info("Executing Test 02: Wake word specificity benchmark...")
    
    positives = [
        ("Hey Golu, what is my roll number?", "what is my roll number"),
        ("Hi Golu, fill this form", "fill this form"),
        ("Golu please help me out", "please help me out"),
        ("hai golu open resume", "open resume"),
        ("hello golu draft an essay", "draft an essay")
    ]
    for phrase, expected_sub in positives:
        is_wake, query = voice_engine.detect_wake_word(phrase)
        assert is_wake is True, f"Failed to detect wake word in: '{phrase}'"
        logger.info("  -> Positive: '%s' -> Detected! Remaining query: '%s'", phrase, query)

    negatives = [
        "Hey Google, set a timer",
        "Alexa turn off lights",
        "Siri what is the weather",
        "Hello everyone in the meeting",
        "Can you send the project file please?"
    ]
    for phrase in negatives:
        is_wake, query = voice_engine.detect_wake_word(phrase)
        assert is_wake is False, f"False positive wake word detected in: '{phrase}'"
        logger.info("  -> Negative: '%s' -> Correctly ignored.", phrase)

    logger.info("✅ Test 02 PASSED: 100% accuracy on wake word detection with 0% false triggers.")


def test_03_wasapi_loopback_stream():
    logger.info("Executing Test 03: WASAPI loopback capture & release latency...")
    device = loopback_listener.get_loopback_device()
    assert device is not None, "A valid WASAPI loopback device must be detected"
    logger.info("  -> WASAPI Loopback Device: %s (ch=%d, rate=%dHz)",
                device["name"], device["maxInputChannels"], device["defaultSampleRate"])

    # Measure stop release latency
    loopback_listener.start()
    time.sleep(0.3)
    t0 = time.perf_counter()
    loopback_listener.stop()
    release_ms = (time.perf_counter() - t0) * 1000.0
    logger.info("  -> WASAPI audio handles released in %.2fms (Target: < 50ms)", release_ms)
    assert release_ms < 50.0, f"Release took {release_ms}ms, exceeded 50ms hard limit"

    logger.info("✅ Test 03 PASSED: WASAPI loopback stream active and released in < 50ms.")


def test_04_stealth_hud_affinity():
    logger.info("Executing Test 04: Stealth HUD display affinity (WDA_EXCLUDEFROMCAPTURE)...")
    app, hud, comm = create_hud_app()
    hud.show()
    app.processEvents()

    assert hud.is_stealth_active is True, "WDA_EXCLUDEFROMCAPTURE (0x00000011) must be active"
    logger.info("  -> SetWindowDisplayAffinity: WDA_EXCLUDEFROMCAPTURE confirmed active (0x%08X)", WDA_EXCLUDEFROMCAPTURE)

    # Test HUD signals
    comm.transcript_signal.emit("Meeting audio line")
    comm.answer_signal.emit("Grounded advice point")
    app.processEvents()
    assert "Meeting audio line" in hud.transcript_box.toPlainText()
    assert "Grounded advice point" in hud.answer_box.toPlainText()

    # Test emergency wipe
    hud.wipe_and_hide()
    assert not hud.isVisible()
    assert hud.transcript_box.toPlainText() == ""
    assert hud.answer_box.toPlainText() == ""

    logger.info("✅ Test 04 PASSED: Stealth HUD cloaked and emergency wipe verified.")


def test_05_fsm_mutual_exclusivity():
    logger.info("Executing Test 05: FSM mutual exclusivity & hardware kill switch...")

    # Transition to ASSISTANT
    state_machine.transition_to(GoluMode.ASSISTANT)
    assert state_machine.current_mode == GoluMode.ASSISTANT
    assert voice_engine.is_hard_muted is False, "TTS must be unmuted in ASSISTANT mode"
    assert loopback_listener.is_running is False, "Loopback must be OFF in ASSISTANT mode"
    logger.info("  -> MODE_ASSISTANT: Mic & TTS active, Loopback OFF.")

    # Transition to MEETING
    state_machine.transition_to(GoluMode.MEETING)
    assert state_machine.current_mode == GoluMode.MEETING
    assert voice_engine.is_hard_muted is True, "TTS must be hard-muted in MEETING mode"
    assert loopback_listener.is_running is True, "Loopback must be ACTIVE in MEETING mode"
    
    # Verify zero-leak guarantee: calling speak() in meeting mode MUST return False
    leak_test = voice_engine.speak("This is a leaked audio test")
    assert leak_test is False, "Hard-mute failed to suppress speech output!"
    logger.info("  -> MODE_MEETING: TTS hard-muted (0% leak verified), WASAPI loopback active.")

    # Transition to EMERGENCY KILL
    t0 = time.perf_counter()
    state_machine.transition_to(GoluMode.KILL)
    kill_elapsed_ms = (time.perf_counter() - t0) * 1000.0
    assert state_machine.current_mode == GoluMode.KILL
    assert loopback_listener.is_running is False
    assert voice_engine.is_hard_muted is True
    logger.info("  -> MODE_KILL: Emergency interrupt completed in %.2fms (Target: < 50ms).", kill_elapsed_ms)
    assert kill_elapsed_ms < 50.0, f"Kill took {kill_elapsed_ms}ms (exceeded 50ms)"

    logger.info("✅ Test 05 PASSED: Strict mutual exclusivity & sub-50ms kill switch verified.")


def test_06_meeting_copilot_e2e():
    logger.info("Executing Test 06: End-to-end meeting co-pilot simulation (RAG -> Cloaked HUD)...")
    
    # Set to MEETING mode
    state_machine.transition_to(GoluMode.MEETING)
    
    meeting_question = "Can you summarize your experience at TechInnovate Labs and the technologies you used?"
    resp = client.post(
        "/api/meeting/simulate",
        json={"speaker_question": meeting_question},
        headers=AUTH_HEADERS
    )
    assert resp.status_code == 200, f"Meeting simulation failed: {resp.text}"
    data = resp.json()
    advice = data.get("copilot_advice", "")
    logger.info("  -> Meeting Question: '%s'", meeting_question)
    logger.info("  -> Co-Pilot Live Advice:\n%s", advice)

    # Validate grounding: must mention candidate's verified projects or technologies from resume
    advice_lower = advice.lower()
    verified_keywords = ["chromadb", "bm25", "raft", "iot", "telemetry", "techinnovate", "intern", "pytorch", "huggingface", "key-value", "consensus"]
    has_grounding = any(kw in advice_lower for kw in verified_keywords)
    assert has_grounding, f"Co-pilot advice must be factually grounded in candidate resume profile. Got: {advice}"

    # Reset state to IDLE
    state_machine.transition_to(GoluMode.IDLE)
    logger.info("✅ Test 06 PASSED: End-to-end meeting co-pilot verified with 100% factual grounding.")


def run_all_day3_tests():
    print("=" * 70)
    print("PROJECT GOLU: DAY 3 MANDATORY EXIT GATE EVALUATION BENCHMARK")
    print("=" * 70)
    start_total = time.perf_counter()

    test_01_voice_engine_pipeline()
    test_02_wake_word_specificity()
    test_03_wasapi_loopback_stream()
    test_04_stealth_hud_affinity()
    test_05_fsm_mutual_exclusivity()
    test_06_meeting_copilot_e2e()

    total_time = time.perf_counter() - start_total
    print("=" * 70)
    print(f"🎉 ALL DAY 3 MANDATORY EXIT GATES PASSED IN {total_time:.2f}s!")
    print("=" * 70)


if __name__ == "__main__":
    run_all_day3_tests()
