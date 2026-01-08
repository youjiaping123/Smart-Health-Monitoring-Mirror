#!/usr/bin/env python3
"""
Smart Health Monitoring Mirror - Main Entry Point
Graduation Project
"""

import os
import sys
import time
import signal
import threading
import argparse
from multiprocessing import Process, Event

import yaml

from modules import HardwareIO, VisionService, AudioService, AlertManager
from utils.logger import setup_logger


class HealthMirror:
    """Main application controller"""

    def __init__(self, config_path="config.yaml"):
        self.config_path = config_path  # Save config path for modules
        self.config = self._load_config(config_path)
        self.logger = setup_logger(
            "main",
            self.config["system"]["log_level"],
            self.config["system"]["log_dir"]
        )

        self.logger.info("=" * 60)
        self.logger.info("Smart Health Monitoring Mirror")
        self.logger.info(f"Version: {self.config['system']['version']}")
        self.logger.info("=" * 60)

        # Initialize modules
        self.hardware = None
        self.audio = None
        self.alert_manager = None
        self.vision_process = None
        self.vision_stop_event = Event()  # For graceful vision shutdown
        self._wake_word_thread = None
        self._button_monitoring = True

        # Signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _load_config(self, path):
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    def _signal_handler(self, sig, frame):
        """Handle shutdown signals"""
        self.logger.info(f"Received signal {sig}, shutting down...")
        self.shutdown()
        sys.exit(0)

    def _start_vision_process(self):
        """Start vision service in separate process"""
        config_path = self.config_path  # Capture for closure
        stop_event = self.vision_stop_event  # Capture stop event

        def run_vision():
            try:
                vision = VisionService(config_path, stop_event)
                vision.run()
            except Exception as e:
                print(f"Vision process error: {e}")  # Logger not available in subprocess

        self.vision_process = Process(target=run_vision, daemon=True)
        self.vision_process.start()
        self.logger.info(f"Vision process started (PID: {self.vision_process.pid})")

    def _wake_word_listener(self):
        """Wake word detection thread"""
        self.logger.info("Wake word listener started")

        while self._button_monitoring:
            try:
                detected = self.audio.listen_for_wake_word()
                if detected:
                    self.logger.info("Wake word detected!")
                    self._handle_wake_word()
            except Exception as e:
                self.logger.error(f"Wake word listener error: {e}")
                time.sleep(1)

    def _handle_wake_word(self):
        """Handle wake word detection"""
        # Visual feedback
        self.hardware.led_blink([255, 255, 0], count=2, interval=0.1)

        # Listen for command
        command = self.audio.listen_for_command(timeout=5)

        if not command:
            self.audio.speak("I didn't catch that. Please try again.")
            return

        self.logger.info(f"Command received: {command}")
        self._process_command(command)

    def _process_command(self, command):
        """Process voice commands"""
        cmd_lower = command.lower()

        if "status" in cmd_lower or "how am i" in cmd_lower:
            level = self.alert_manager.get_current_level()
            messages = {
                "normal": "Everything looks normal. You seem alert and well.",
                "mild": "You're showing mild signs of fatigue. Consider taking a break soon.",
                "severe": "You appear quite fatigued. Please take a break immediately."
            }
            self.audio.speak(messages.get(level, "Status unknown."))

        elif "okay" in cmd_lower or "fine" in cmd_lower:
            self.audio.speak("Glad to hear it. I'll continue monitoring.")
            self.alert_manager.force_alert("normal")

        elif "timer" in cmd_lower:
            # Extract duration (simplified)
            self.audio.speak("Timer feature coming soon.")

        elif "stop" in cmd_lower or "sleep" in cmd_lower:
            self.audio.speak("Stopping monitoring. Say the wake word to restart.")
            self.alert_manager.force_alert("normal")

        else:
            self.audio.speak("I'm sorry, I didn't understand that command.")

    def _setup_button_handlers(self):
        """Setup button event handlers"""

        def on_single_press():
            self.logger.info("Button: Single press")
            level = self.alert_manager.get_current_level()
            if level in ["mild", "severe"]:
                # Acknowledge alert
                self.alert_manager.force_alert("normal")
                self.audio.speak("Alert dismissed.")
            else:
                # Quick status check
                self.audio.speak("Performing quick health check.")

        def on_double_press():
            self.logger.info("Button: Double press")
            level = self.alert_manager.get_current_level()
            self.audio.speak(f"Current status: {level}")

        def on_long_press():
            self.logger.info("Button: Long press")
            self.audio.speak("Toggling monitoring mode.")

        def on_very_long_press():
            self.logger.info("Button: Very long press - shutting down")
            self.audio.speak("Shutting down. Goodbye.")
            self.shutdown()
            sys.exit(0)

        self.hardware.on_button_event("single", on_single_press)
        self.hardware.on_button_event("double", on_double_press)
        self.hardware.on_button_event("long", on_long_press)
        self.hardware.on_button_event("very_long", on_very_long_press)

    def start(self):
        """Start the health mirror system"""
        try:
            # Initialize hardware
            self.logger.info("Initializing hardware...")
            self.hardware = HardwareIO(self.config_path)
            self.hardware.set_led_color([0, 255, 0], 50)  # Green startup indicator

            # Initialize audio
            self.logger.info("Initializing audio...")
            self.audio = AudioService(self.config_path)
            self.audio.speak("System initializing.")

            # Initialize alert manager
            self.logger.info("Initializing alert manager...")
            self.alert_manager = AlertManager(self.config_path)
            self.alert_manager.start(self.hardware, self.audio)

            # Setup button handlers
            self._setup_button_handlers()

            # Start vision process
            self.logger.info("Starting vision service...")
            self._start_vision_process()
            time.sleep(2)  # Allow vision service to initialize

            # Start wake word listener
            self.logger.info("Starting wake word listener...")
            self._wake_word_thread = threading.Thread(
                target=self._wake_word_listener,
                daemon=True
            )
            self._wake_word_thread.start()

            # System ready
            self.hardware.set_led_color([0, 255, 0], 100)  # Bright green
            self.audio.speak("System ready. Monitoring started.")
            self.logger.info("System fully operational")

            # Main loop
            while True:
                time.sleep(1)

        except KeyboardInterrupt:
            self.logger.info("Interrupted by user")
            self.shutdown()
        except Exception as e:
            self.logger.exception(f"Fatal error: {e}")
            self.shutdown()
            raise

    def shutdown(self):
        """Shutdown all services"""
        self.logger.info("Shutting down system...")

        # Stop monitoring threads
        self._button_monitoring = False

        # Stop services
        if self.alert_manager:
            self.alert_manager.stop()

        # Gracefully stop vision process
        if self.vision_process and self.vision_process.is_alive():
            self.logger.info("Requesting vision process to stop...")
            self.vision_stop_event.set()  # Signal the process to stop
            self.vision_process.join(timeout=5)  # Wait for graceful exit

            if self.vision_process.is_alive():
                self.logger.warning("Vision process did not exit gracefully, terminating...")
                self.vision_process.terminate()
                self.vision_process.join(timeout=2)
            else:
                self.logger.info("Vision process stopped gracefully")

        # Cleanup hardware
        if self.hardware:
            self.hardware.set_led_color([0, 0, 0], 0)  # Turn off LEDs
            self.hardware.cleanup()

        # Cleanup audio
        if self.audio:
            self.audio.cleanup()

        self.logger.info("System shutdown complete")


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description="Smart Health Monitoring Mirror")
    parser.add_argument(
        "--config",
        default="config.yaml",
        help="Path to configuration file"
    )
    parser.add_argument(
        "--test-hardware",
        action="store_true",
        help="Run hardware test mode"
    )
    parser.add_argument(
        "--test-audio",
        action="store_true",
        help="Run audio test mode"
    )

    args = parser.parse_args()

    # Test modes
    if args.test_hardware:
        print("Testing hardware...")
        hw = HardwareIO(args.config)
        print("Green LED")
        hw.set_led_color([0, 255, 0], 100)
        time.sleep(2)
        print("Yellow LED")
        hw.set_led_color([255, 255, 0], 100)
        time.sleep(2)
        print("Red LED")
        hw.set_led_color([255, 0, 0], 100)
        time.sleep(2)
        print("LED Breathing")
        hw.led_breathing([255, 0, 0], duration=5)
        hw.cleanup()
        print("Hardware test complete")
        return

    if args.test_audio:
        print("Testing audio...")
        audio = AudioService(args.config)
        audio.speak("Hello, I am your smart health monitoring mirror.")
        audio.speak("This is a test of the text to speech system.")
        audio.cleanup()
        print("Audio test complete")
        return

    # Normal operation
    app = HealthMirror(config_path=args.config)
    app.start()


if __name__ == "__main__":
    main()
