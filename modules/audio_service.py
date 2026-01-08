import os
import subprocess
import time
import json
import struct
import uuid
import threading
import yaml

try:
    import pyaudio
    PYAUDIO_AVAILABLE = True
except ImportError:
    PYAUDIO_AVAILABLE = False
    print("WARNING: PyAudio not available")

try:
    import pvporcupine
    PORCUPINE_AVAILABLE = True
except ImportError:
    PORCUPINE_AVAILABLE = False
    print("WARNING: Porcupine not available")

try:
    from vosk import Model, KaldiRecognizer
    VOSK_AVAILABLE = True
except ImportError:
    VOSK_AVAILABLE = False
    print("WARNING: Vosk not available")

from utils.logger import setup_logger


class AudioService:
    """Audio service for wake word detection, ASR, and TTS"""

    def __init__(self, config_path="config.yaml"):
        self.config = self._load_config(config_path)
        self.logger = setup_logger(
            "audio_service",
            self.config["system"]["log_level"],
            self.config["system"]["log_dir"]
        )

        self.audio_config = self.config["audio"]
        self._pa = None
        self._porcupine = None
        self._vosk_model = None
        self._recognizer = None
        self.audio_stream = None
        self._current_sample_rate = None  # Track current stream parameters
        self._current_frame_length = None
        self._tts_lock = threading.Lock()  # Serialize TTS calls

        self._init_audio()

    def _load_config(self, path):
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    def _init_audio(self):
        """Initialize audio components"""
        if not PYAUDIO_AVAILABLE:
            self.logger.warning("PyAudio not available - audio disabled")
            return

        self._pa = pyaudio.PyAudio()

        # Initialize Porcupine wake word detector
        if PORCUPINE_AVAILABLE:
            try:
                porc_cfg = self.audio_config["porcupine"]
                access_key = porc_cfg.get("access_key", "")

                if access_key and "YOUR_" not in access_key:
                    self._porcupine = pvporcupine.create(
                        access_key=access_key,
                        keywords=[self.audio_config["wake_word"].replace(" ", "-")]
                    )
                    self.logger.info("Porcupine wake word detector initialized")
                else:
                    self.logger.warning("Porcupine API key not configured")
            except Exception as e:
                self.logger.error(f"Failed to initialize Porcupine: {e}")

        # Initialize Vosk speech recognition
        if VOSK_AVAILABLE:
            try:
                vosk_cfg = self.audio_config["vosk"]
                model_path = vosk_cfg["model_path"]

                if os.path.isdir(model_path):
                    self._vosk_model = Model(model_path)
                    sample_rate = vosk_cfg["sample_rate"]
                    self._recognizer = Kaldi Recognizer(self._vosk_model, sample_rate)
                    self._recognizer.SetWords(True)
                    self.logger.info("Vosk ASR initialized")
                else:
                    self.logger.warning(f"Vosk model not found: {model_path}")
            except Exception as e:
                self.logger.error(f"Failed to initialize Vosk: {e}")

    def _open_stream(self, sample_rate=None, frame_length=None):
        """Open audio input stream with parameter change detection"""
        if not PYAUDIO_AVAILABLE:
            return

        # Determine target parameters
        target_sample_rate = sample_rate or (self._porcupine.sample_rate if self._porcupine else 16000)
        target_frame_length = frame_length or (self._porcupine.frame_length if self._porcupine else 512)

        # Check if stream needs to be reopened due to parameter change
        if self.audio_stream and self.audio_stream.is_active():
            if (target_sample_rate != self._current_sample_rate or
                target_frame_length != self._current_frame_length):
                # Parameters changed, close and reopen
                self.logger.debug(f"Audio stream parameters changed, reopening stream")
                self.audio_stream.close()
                self.audio_stream = None

        # Open new stream if needed
        if not self.audio_stream or not self.audio_stream.is_active():
            try:
                self.audio_stream = self._pa.open(
                    rate=target_sample_rate,
                    channels=1,
                    format=pyaudio.paInt16,
                    input=True,
                    frames_per_buffer=target_frame_length
                )
                self._current_sample_rate = target_sample_rate
                self._current_frame_length = target_frame_length
                self.logger.debug(f"Audio stream opened: {target_sample_rate}Hz, buffer={target_frame_length}")
            except Exception as e:
                self.logger.error(f"Failed to open audio stream: {e}")

    def listen_for_wake_word(self, timeout=0.1):
        """Listen for wake word (non-blocking)"""
        if not self._porcupine:
            time.sleep(timeout)
            return False

        self._open_stream()

        try:
            pcm = self.audio_stream.read(
                self._porcupine.frame_length,
                exception_on_overflow=False
            )
            pcm = struct.unpack_from("h" * self._porcupine.frame_length, pcm)
            keyword_index = self._porcupine.process(pcm)
            return keyword_index >= 0
        except Exception as e:
            self.logger.error(f"Wake word detection error: {e}")
            return False

    def listen_for_command(self, timeout=5):
        """Listen for voice command after wake word"""
        if not self._recognizer:
            self.logger.warning("Vosk ASR not available")
            return ""

        self._open_stream(
            sample_rate=self.audio_config["vosk"]["sample_rate"],
            frame_length=512
        )

        self.logger.info("Listening for command...")
        start_time = time.time()

        try:
            while time.time() - start_time < timeout:
                pcm_chunk = self.audio_stream.read(512, exception_on_overflow=False)

                if self._recognizer.AcceptWaveform(pcm_chunk):
                    res = json.loads(self._recognizer.Result())
                    command = res.get('text', '').strip()
                    if command:
                        self.logger.info(f"Command recognized: {command}")
                        return command

            # Get final result
            res = json.loads(self._recognizer.FinalResult())
            command = res.get('text', '').strip()
            if command:
                self.logger.info(f"Command recognized (final): {command}")
            return command
        except Exception as e:
            self.logger.error(f"Command recognition error: {e}")
            return ""

    def speak(self, text):
        """Text-to-speech using PicoTTS (thread-safe)"""
        with self._tts_lock:  # Serialize TTS to prevent file conflicts
            self.logger.info(f"TTS: {text}")

            tts_cfg = self.audio_config["tts"]
            engine = tts_cfg["engine"]

            if engine == "pico":
                self._speak_pico(text)
            elif engine == "espeak":
                self._speak_espeak(text)
            else:
                self.logger.warning(f"Unknown TTS engine: {engine}")

    def _speak_pico(self, text):
        """Speak using PicoTTS (pico2wave)"""
        wav_file = f"/tmp/health_mirror_tts_{uuid.uuid4().hex[:8]}.wav"  # Unique filename
        try:
            # Generate WAV
            subprocess.run(
                ["pico2wave", "-w", wav_file, text],
                check=True,
                capture_output=True,
                text=True
            )
            # Play WAV
            subprocess.run(
                ["aplay", "-q", wav_file],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
        except FileNotFoundError:
            self.logger.error("pico2wave or aplay not found. Install with: sudo apt-get install libttspico-utils alsa-utils")
        except subprocess.CalledProcessError as e:
            self.logger.error(f"TTS error: {e}")
        finally:
            if os.path.exists(wav_file):
                os.remove(wav_file)

    def _speak_espeak(self, text):
        """Speak using eSpeak"""
        try:
            subprocess.run(
                ["espeak", text],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
        except FileNotFoundError:
            self.logger.error("espeak not found. Install with: sudo apt-get install espeak")
        except subprocess.CalledProcessError as e:
            self.logger.error(f"eSpeak error: {e}")

    def play_sound(self, sound_file):
        """Play a sound file"""
        if not os.path.exists(sound_file):
            self.logger.warning(f"Sound file not found: {sound_file}")
            return

        try:
            subprocess.run(
                ["aplay", "-q", sound_file],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
        except Exception as e:
            self.logger.error(f"Failed to play sound: {e}")

    def cleanup(self):
        """Cleanup audio resources"""
        if self._porcupine:
            self._porcupine.delete()
        if self.audio_stream:
            self.audio_stream.close()
        if self._pa:
            self._pa.terminate()
        self.logger.info("Audio service cleaned up")

    def __del__(self):
        self.cleanup()


if __name__ == "__main__":
    # Test script
    service = AudioService()
    service.speak("Hello, I am your health monitoring mirror.")
    time.sleep(1)
    service.cleanup()
