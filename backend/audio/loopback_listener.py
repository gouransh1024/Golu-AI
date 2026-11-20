"""Project Golu: PyAudioWPatch WASAPI Speaker Loopback Audio Listener.
Captures system speaker audio (WhatsApp, Google Meet, Zoom, MS Teams calls)
at the driver level without routing through a physical microphone.
Strictly active during MODE_MEETING; stopped in MODE_ASSISTANT / MODE_KILL.
"""

import time
import threading
import atexit
import logging
from typing import Callable, Optional

logger = logging.getLogger("golu.audio.loopback")


class WASAPILoopbackListener:
    """Windows WASAPI Loopback Audio Listener using PyAudioWPatch with C-level stream callbacks."""

    def __init__(self, callback: Optional[Callable[[bytes, int, int], None]] = None):
        self.callback = callback
        self.is_running: bool = False
        self._pyaudio_instance = None
        self._stream = None
        self._lock = threading.Lock()
        atexit.register(self.terminate)

    def _get_pyaudio(self):
        """Lazy-inits persistent PyAudio instance."""
        if self._pyaudio_instance is None:
            import pyaudiowpatch as pyaudio
            self._pyaudio_instance = pyaudio.PyAudio()
        return self._pyaudio_instance

    def get_loopback_device(self, p=None):
        """Discovers default speakers and finds corresponding WASAPI loopback device."""
        import pyaudiowpatch as pyaudio
        p = p or self._get_pyaudio()

        wasapi_info = p.get_host_api_info_by_type(pyaudio.paWASAPI)
        default_speakers = p.get_device_info_by_index(wasapi_info["defaultOutputDevice"])
        
        if not default_speakers.get("isLoopbackDevice", False):
            for loopback in p.get_loopback_device_info_generator():
                if default_speakers["name"] in loopback["name"]:
                    return loopback
            for loopback in p.get_loopback_device_info_generator():
                return loopback
        return default_speakers

    def start(self):
        """Starts loopback capture via non-blocking PortAudio stream callback."""
        with self._lock:
            if self.is_running and self._stream is not None and self._stream.is_active():
                logger.warning("WASAPI Loopback listener is already active.")
                return

            import pyaudiowpatch as pyaudio
            p = self._get_pyaudio()
            device_info = self.get_loopback_device(p)
            if not device_info:
                logger.error("No suitable WASAPI loopback device found.")
                return

            channels = int(device_info["maxInputChannels"])
            sample_rate = int(device_info["defaultSampleRate"])

            def _portaudio_callback(in_data, frame_count, time_info, status_flags):
                if self.is_running and self.callback:
                    try:
                        self.callback(in_data, sample_rate, channels)
                    except Exception as e:
                        logger.debug("Loopback callback exception: %s", e)
                return (None, pyaudio.paContinue if self.is_running else pyaudio.paComplete)

            try:
                if self._stream is not None:
                    try:
                        self._stream.stop_stream()
                        self._stream.close()
                    except Exception:
                        pass

                self.is_running = True
                self._stream = p.open(
                    format=pyaudio.paInt16,
                    channels=channels,
                    rate=sample_rate,
                    input=True,
                    input_device_index=device_info["index"],
                    frames_per_buffer=1024,
                    stream_callback=_portaudio_callback
                )
                self._stream.start_stream()
                logger.info("WASAPI Loopback stream started on %s (ch=%d, rate=%dHz)", device_info["name"], channels, sample_rate)
            except Exception as e:
                self.is_running = False
                logger.error("Failed to start WASAPI loopback stream: %s", e)

    def stop(self):
        """Stops loopback stream and closes handles within 50ms."""
        start_t = time.perf_counter()
        with self._lock:
            self.is_running = False
            if self._stream is not None:
                try:
                    self._stream.stop_stream()
                    self._stream.close()
                except Exception as e:
                    logger.debug("Error stopping loopback stream: %s", e)
                finally:
                    self._stream = None

        elapsed_ms = (time.perf_counter() - start_t) * 1000.0
        logger.info("WASAPI Loopback stream closed cleanly in %.2fms.", elapsed_ms)

    def terminate(self):
        """Terminates PyAudio runtime upon process exit."""
        self.stop()
        if self._pyaudio_instance is not None:
            try:
                self._pyaudio_instance.terminate()
            except Exception:
                pass
            self._pyaudio_instance = None


# Global Loopback Listener instance
loopback_listener = WASAPILoopbackListener()
