import time
import threading
import yaml

from utils.ipc import ZmqSubscriber
from utils.logger import setup_logger


class AlertManager:
    """Alert manager for handling fatigue alerts and triggering LED/audio feedback"""

    def __init__(self, config_path="config.yaml"):
        self.config = self._load_config(config_path)
        self.logger = setup_logger(
            "alert_manager",
            self.config["system"]["log_level"],
            self.config["system"]["log_dir"]
        )

        self.alerts_config = self.config["alerts"]
        self.current_level = "normal"
        self.last_alert_time = 0
        self._running = False
        self._thread = None
        self._state_lock = threading.Lock()  # Protect state updates
        self.subscriber = None  # Initialize subscriber

        self.logger.info("Alert manager initialized")

    def _load_config(self, path):
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    def start(self, hardware_io, audio_service):
        """Start alert manager with hardware and audio services"""
        self.hardware_io = hardware_io
        self.audio_service = audio_service
        self._running = True

        # Subscribe to vision metrics
        ipc_endpoint = f"tcp://localhost:{self.config['ipc']['vision_port']}"
        self.subscriber = ZmqSubscriber(ipc_endpoint)

        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self.logger.info("Alert manager started")

    def stop(self):
        """Stop alert manager"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
        if self.subscriber:  # Guard against uninitialized subscriber
            self.subscriber.close()
        self.logger.info("Alert manager stopped")

    def _run(self):
        """Main processing loop"""
        while self._running:
            # Receive vision metrics
            msg = self.subscriber.recv(timeout_ms=1000)
            if not msg:
                continue

            topic = msg.get("topic", "")
            if topic != "vision.metrics":
                continue

            payload = msg.get("payload", {})
            self._process_metrics(payload)

    def _process_metrics(self, metrics):
        """Process fatigue metrics and trigger alerts"""
        fatigue_level = metrics.get("fatigue_level", "normal")
        face_detected = metrics.get("face_detected", False)

        if not face_detected:
            # No face - return to normal if needed
            if self.current_level != "normal":
                self._update_alert_level("normal")
            return

        # Update alert level if changed
        if fatigue_level != self.current_level:
            self._update_alert_level(fatigue_level)

    def _update_alert_level(self, new_level):
        """Update alert level and trigger appropriate feedback (thread-safe)"""
        with self._state_lock:
            old_level = self.current_level
            self.current_level = new_level

            self.logger.info(f"Alert level changed: {old_level} -> {new_level}")

            # Get alert configuration
            alert_cfg = self.alerts_config["levels"].get(new_level, {})

            # Update LED
            led_color = alert_cfg.get("led_color", [0, 255, 0])
            led_mode = alert_cfg.get("led_mode", "solid")

            if led_mode == "solid":
                self.hardware_io.set_led_color(led_color, 100)
            elif led_mode == "breathing":
                threading.Thread(
                    target=self.hardware_io.led_breathing,
                    args=(led_color,),
                    daemon=True
                ).start()
            elif led_mode == "blink":
                threading.Thread(
                    target=self.hardware_io.led_blink,
                    args=(led_color,),
                    daemon=True
                ).start()

            # Voice alert (with rate limiting)
            now = time.time()
            repeat_interval = self.alerts_config.get("repeat_interval", 60)

            if now - self.last_alert_time > repeat_interval:
                voice_message = alert_cfg.get("voice_message", "")
                if voice_message and new_level != "normal":
                    threading.Thread(
                        target=self.audio_service.speak,
                        args=(voice_message,),
                        daemon=True
                    ).start()
                    self.last_alert_time = now

    def force_alert(self, level):
        """Manually force an alert level"""
        self._update_alert_level(level)

    def get_current_level(self):
        """Get current alert level (thread-safe)"""
        with self._state_lock:
            return self.current_level


if __name__ == "__main__":
    # Test script
    manager = AlertManager()
    print(f"Current alert level: {manager.get_current_level()}")
