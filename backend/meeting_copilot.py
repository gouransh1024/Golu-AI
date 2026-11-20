"""Project Golu: Meeting Co-Pilot Processing Pipeline.
Processes WASAPI speaker audio, transcribes with Faster-Whisper,
retrieves grounded resume/project context via Hybrid RAG,
and streams concise bulleted talking points to the invisible Stealth HUD.
"""

import time
import logging
from typing import Optional, Tuple
import numpy as np

from backend.audio.golu_voice import voice_engine
from backend.audio.loopback_listener import loopback_listener
from backend.security import security_manager
from backend.memory.rag_store import rag_store
from backend.llm_engine import llm_engine

logger = logging.getLogger("golu.meeting_copilot")

COPILOT_PROMPT = """You are Golu, an invisible real-time meeting co-pilot.
A meeting participant or interviewer just asked the following question:
<untrusted_input>
{question}
</untrusted_input>

Ground your answer STRICTLY in the candidate's verified profile data:
<verified_facts>
{context}
</verified_facts>

Rules for Co-Pilot output:
1. Provide 2 to 3 concise, high-impact bullet points the candidate can glance at and speak naturally.
2. Under 50 words total.
3. Include specific metrics, numbers, and technologies from the profile.
4. No intro or pleasantries.
"""


class MeetingCoPilot:
    """End-to-end co-pilot orchestrator for live calls."""

    def __init__(self, hud_communicator=None):
        self.hud_communicator = hud_communicator
        self.is_active: bool = False
        self._audio_buffer = bytearray()
        self._min_buffer_bytes = 16000 * 2 * 2  # 2 seconds of 16kHz 16-bit audio

    def set_hud_communicator(self, communicator):
        self.hud_communicator = communicator

    def process_speaker_audio_chunk(self, chunk: bytes, sample_rate: int, channels: int):
        """Callback fed by WASAPI Loopback Listener."""
        if not self.is_active:
            return

        # VAD filter
        rms = voice_engine.compute_vad_rms(chunk)
        if rms < 250.0:
            # Silence or background hum, ignore to save CPU
            return

        self._audio_buffer.extend(chunk)
        if len(self._audio_buffer) >= self._min_buffer_bytes:
            buffer_to_process = bytes(self._audio_buffer)
            self._audio_buffer.clear()
            self._handle_audio_segment(buffer_to_process, sample_rate, channels)

    def _handle_audio_segment(self, audio_bytes: bytes, sample_rate: int, channels: int):
        """Transcribes audio and triggers co-pilot suggestion."""
        # Convert to mono 16kHz if needed
        audio_data = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        if channels > 1:
            audio_data = audio_data.reshape(-1, channels).mean(axis=1)

        transcript, lang, _ = voice_engine.transcribe(audio_data, sample_rate=sample_rate)
        if transcript.strip():
            logger.info("Meeting speech detected: '%s'", transcript)
            if self.hud_communicator:
                self.hud_communicator.transcript_signal.emit(transcript)
            
            # Generate answer if it looks like a question or prompt
            self.generate_copilot_advice(transcript)

    def generate_copilot_advice(self, query: str) -> str:
        """Grounds query in RAG and generates concise talking points for the HUD."""
        start_t = time.perf_counter()
        clean_query = security_manager.sanitize_input(query)

        # Retrieve verified facts from ChromaDB + BM25
        rag_results = rag_store.hybrid_search(clean_query, top_k=3)
        context_text = "\n".join([f"- {r['text']}" for r in rag_results])

        prompt = COPILOT_PROMPT.format(question=clean_query, context=context_text)
        system_instruction = "You are Golu Meeting Co-Pilot. Return exactly 2-3 concise talking point bullets."
        
        answer = llm_engine.generate(
            prompt=prompt,
            system_prompt=system_instruction,
            max_tokens=150
        )

        latency = time.perf_counter() - start_t
        logger.info("Co-Pilot advice generated in %.2fs: '%s'", latency, answer[:80])

        if self.hud_communicator:
            self.hud_communicator.answer_signal.emit(answer)

        return answer


# Global Meeting Co-Pilot instance
meeting_copilot = MeetingCoPilot()
