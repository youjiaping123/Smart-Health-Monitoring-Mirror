import time
import threading
import yaml

try:
    import RPi.GPIO as GPIO
    GPIO_AVAILABLE = True
except (ImportError, RuntimeError):
    GPIO_AVAILABLE = False
    print("WARNING: RPi.GPIO not available. Running in simulation mode.")

from utils.logger import setup_logger


class HardwareIO:
    """Hardware I/O controller for LED and Button"""

    def __init__(self, config_path="config.yaml"):
        self.config = self._load_config(config_path)
        self.logger = setup_logger(
            "hardware_io",
            self.config["system"]["log_level"],
            self.config["system"]["log_dir"]
        )

        self.gpio_config = self.config["hardware"]
        self._lock = threading.Lock()
        self._button_callbacks = {
            "single": None,
            "double": None,
            "long": None,
            "very_long": None
        }

        if GPIO_AVAILABLE:
            self._setup_gpio()
        else:
            self.logger.warning("GPIO not available - running in simulation mode")

    def _load_config(self, path):
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    def _setup_gpio(self):
        mode_str = self.gpio_config["gpio_mode"]
        mode = GPIO.BCM if mode_str == "BCM" else GPIO.BOARD
        GPIO.setmode(mode)
        GPIO.setwarnings(False)

        self._setup_leds()
        self._setup_button()

    def _setup_leds(self):
        self.led_pins = self.gpio_config["led"]
        for color in ["red_pin", "green_pin", "blue_pin"]:
            pin = self.led_pins[color]
            GPIO.setup(pin, GPIO.OUT)
            GPIO.output(pin, GPIO.LOW)

        # PWM for breathing effect
        self.led_pwm = {
            "red": GPIO.PWM(self.led_pins["red_pin"], self.led_pins["pwm_frequency"]),
            "green": GPIO.PWM(self.led_pins["green_pin"], self.led_pins["pwm_frequency"]),
            "blue": GPIO.PWM(self.led_pins["blue_pin"], self.led_pins["pwm_frequency"]),
        }
        for pwm in self.led_pwm.values():
            pwm.start(0)

    def _setup_button(self):
        btn_config = self.gpio_config["button"]
        self.button_pin = btn_config["pin"]
        pull = GPIO.PUD_UP if btn_config["pull_up_down"] == "PUD_UP" else GPIO.PUD_DOWN

        GPIO.setup(self.button_pin, GPIO.IN, pull_up_down=pull)
        GPIO.add_event_detect(
            self.button_pin,
            GPIO.FALLING,
            callback=self._handle_button_event,
            bouncetime=btn_config["bounce_time"],
        )

        self._last_press_time = 0
        self._press_count = 0

    def _handle_button_event(self, channel):
        """Handle button press - non-blocking, delegates to thread"""
        # Don't block GPIO event thread - start processing in separate thread
        threading.Thread(
            target=self._process_button_press,
            args=(time.time(),),
            daemon=True
        ).start()

    def _process_button_press(self, press_start_time):
        """Process button press in separate thread to avoid blocking GPIO events"""
        if not GPIO_AVAILABLE:
            return

        press_duration = 0

        # Wait for release and measure duration
        while GPIO.input(self.button_pin) == GPIO.LOW:
            time.sleep(0.01)
            press_duration = time.time() - press_start_time

        btn_config = self.gpio_config["button"]

        # Check for very long press (shutdown)
        if press_duration >= btn_config["very_long_press_duration"]:
            self._trigger_callback("very_long")
            return

        # Check for long press (toggle mode)
        if press_duration >= btn_config["long_press_duration"]:
            self._trigger_callback("long")
            return

        # Handle single/double click
        now = time.time()
        if now - self._last_press_time < 0.5:  # Within double-click window
            self._press_count += 1
            if self._press_count >= 2:
                self._trigger_callback("double")
                self._press_count = 0
        else:
            self._press_count = 1
            # Delay to detect double click
            threading.Timer(0.5, self._handle_single_click).start()

        self._last_press_time = now

    def _handle_single_click(self):
        if self._press_count == 1:
            self._trigger_callback("single")
        self._press_count = 0

    def _trigger_callback(self, event_type):
        callback = self._button_callbacks.get(event_type)
        if callback:
            try:
                callback()
            except Exception as exc:
                self.logger.exception(f"Button {event_type} callback error: {exc}")

    def on_button_event(self, event_type, callback):
        """Register callback for button events: single, double, long, very_long"""
        if event_type in self._button_callbacks:
            self._button_callbacks[event_type] = callback

    def set_led_color(self, rgb, brightness=100):
        """Set LED to specific RGB color (0-255 each)"""
        if not GPIO_AVAILABLE:
            self.logger.debug(f"LED color: RGB{rgb} @ {brightness}%")
            return

        with self._lock:
            r, g, b = rgb
            self.led_pwm["red"].ChangeDutyCycle(r / 255.0 * brightness)
            self.led_pwm["green"].ChangeDutyCycle(g / 255.0 * brightness)
            self.led_pwm["blue"].ChangeDutyCycle(b / 255.0 * brightness)

    def led_breathing(self, rgb, duration=2.0, steps=50):
        """LED breathing effect"""
        if not GPIO_AVAILABLE:
            return

        # Calculate how many breath cycles we can fit in the duration
        # Each cycle = fade in + fade out ≈ 2 seconds (with steps=50)
        cycle_time = (2.0 * steps) / 50.0  # Approximate cycle duration
        num_cycles = max(1, int(duration / cycle_time))

        for _ in range(num_cycles):
            # Fade in
            for i in range(steps):
                brightness = (i / steps) * 100
                self.set_led_color(rgb, brightness)
                time.sleep(1.0 / steps)
            # Fade out
            for i in range(steps, 0, -1):
                brightness = (i / steps) * 100
                self.set_led_color(rgb, brightness)
                time.sleep(1.0 / steps)

    def led_blink(self, rgb, count=3, interval=0.2):
        """LED blink effect"""
        for _ in range(count):
            self.set_led_color(rgb, 100)
            time.sleep(interval)
            self.set_led_color([0, 0, 0], 0)
            time.sleep(interval)

    def cleanup(self):
        """Cleanup GPIO resources"""
        if GPIO_AVAILABLE:
            for pwm in self.led_pwm.values():
                pwm.stop()
            GPIO.cleanup()
        self.logger.info("Hardware I/O cleaned up")


if __name__ == "__main__":
    # Test script
    io = HardwareIO()
    io.on_button_event("single", lambda: print("Single press!"))
    io.on_button_event("double", lambda: print("Double press!"))
    io.on_button_event("long", lambda: print("Long press!"))

    # Test LEDs
    io.set_led_color([0, 255, 0], 100)  # Green
    time.sleep(1)
    io.set_led_color([255, 255, 0], 100)  # Yellow
    time.sleep(1)
    io.set_led_color([255, 0, 0], 100)  # Red
    time.sleep(1)

    io.cleanup()
