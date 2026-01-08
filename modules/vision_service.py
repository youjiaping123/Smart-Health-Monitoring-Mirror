import os
import time
import threading
from collections import deque

import cv2
import numpy as np
import yaml

try:
    import dlib
    DLIB_AVAILABLE = True
except ImportError:
    DLIB_AVAILABLE = False
    print("WARNING: dlib not available. Face landmarks disabled.")

from utils.ipc import ZmqPublisher
from utils.logger import setup_logger


def eye_aspect_ratio(eye):
    """Calculate Eye Aspect Ratio (EAR) from 6 eye landmarks"""
    a = np.linalg.norm(eye[1] - eye[5])
    b = np.linalg.norm(eye[2] - eye[4])
    c = np.linalg.norm(eye[0] - eye[3])
    return (a + b) / (2.0 * c) if c > 0 else 0.0


def mouth_aspect_ratio(mouth):
    """Calculate Mouth Aspect Ratio (MAR) from 8 mouth landmarks"""
    a = np.linalg.norm(mouth[1] - mouth[7])
    b = np.linalg.norm(mouth[2] - mouth[6])
    c = np.linalg.norm(mouth[3] - mouth[5])
    d = np.linalg.norm(mouth[0] - mouth[4])
    return (a + b + c) / (3.0 * d) if d > 0 else 0.0


class VisionService:
    """Vision service for face detection and fatigue analysis"""

    def __init__(self, config_path="config.yaml", stop_event=None):
        self.stop_event = stop_event  # For graceful shutdown
        self.config = self._load_config(config_path)
        self.logger = setup_logger(
            "vision_service",
            self.config["system"]["log_level"],
            self.config["system"]["log_dir"]
        )

        vcfg = self.config["vision"]

        # Camera settings
        self.camera_id = vcfg["camera_id"]
        self.width = vcfg["resolution"]["width"]
        self.height = vcfg["resolution"]["height"]
        self.fps = vcfg["fps"]
        self.frame_skip = vcfg.get("frame_skip", 1)

        # Detection settings
        face_cfg = vcfg["face_detection"]
        self.detection_method = face_cfg["method"]
        self.confidence_threshold = face_cfg["confidence_threshold"]

        # Fatigue thresholds
        ft_cfg = vcfg["fatigue_thresholds"]
        self.ear_threshold = ft_cfg["ear_threshold"]
        self.mar_threshold = ft_cfg["mar_threshold"]
        self.ear_consec_frames = ft_cfg["ear_consec_frames"]
        self.perclos_window = ft_cfg["perclos_window"]
        self.yawn_threshold = ft_cfg["yawn_threshold"]
        self.yawn_threshold_severe = ft_cfg["yawn_threshold_severe"]

        # Load models
        self._load_models(vcfg)

        # IPC
        ipc_endpoint = f"tcp://*:{self.config['ipc']['vision_port']}"
        self.publisher = ZmqPublisher(ipc_endpoint)

        # State
        self._closed_eyes_counter = 0
        self._blink_count = 0
        self._yawn_history = deque()
        self._eye_closure_history = deque()
        self._frame_count = 0

        self.logger.info("Vision service initialized")

    def _load_config(self, path):
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    def _load_models(self, vcfg):
        """Load face detection and landmark models"""
        face_cfg = vcfg["face_detection"]

        if self.detection_method == "dnn":
            model_path = face_cfg["model_path"]
            weights_path = face_cfg["weights_path"]
            if not os.path.exists(model_path) or not os.path.exists(weights_path):
                self.logger.warning("DNN models not found, falling back to Haar")
                self.detection_method = "haar"

        if self.detection_method == "dnn":
            self.net = cv2.dnn.readNetFromCaffe(face_cfg["model_path"], face_cfg["weights_path"])
            self.logger.info("Loaded DNN face detection model")
        else:
            # Fallback to Haar Cascade
            self.face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
            self.logger.info("Loaded Haar Cascade face detection")

        # Load dlib landmark predictor
        if DLIB_AVAILABLE:
            landmark_path = vcfg["landmark_detection"]["model_path"]
            if os.path.exists(landmark_path):
                self.predictor = dlib.shape_predictor(landmark_path)
                self.logger.info("Loaded dlib landmark predictor")
            else:
                self.logger.warning(f"Landmark model not found: {landmark_path}")
                self.predictor = None
        else:
            self.predictor = None

    def _detect_faces_haar(self, gray):
        """Detect faces using Haar Cascade"""
        faces = self.face_cascade.detectMultiScale(
            gray,
            scaleFactor=1.1,
            minNeighbors=5,
            minSize=(40, 40)
        )
        return [(x, y, x + w, y + h) for (x, y, w, h) in faces]

    def _detect_faces_dnn(self, frame):
        """Detect faces using DNN"""
        blob = cv2.dnn.blobFromImage(
            cv2.resize(frame, (300, 300)),
            1.0, (300, 300), (104.0, 177.0, 123.0)
        )
        self.net.setInput(blob)
        detections = self.net.forward()

        h, w = frame.shape[:2]
        faces = []
        for i in range(detections.shape[2]):
            confidence = detections[0, 0, i, 2]
            if confidence > self.confidence_threshold:
                box = detections[0, 0, i, 3:7] * np.array([w, h, w, h])
                faces.append(box.astype("int"))
        return faces

    def _get_landmarks(self, gray, face_rect):
        """Get 68 facial landmarks using dlib"""
        if not DLIB_AVAILABLE or self.predictor is None:
            return None

        x1, y1, x2, y2 = face_rect
        dlib_rect = dlib.rectangle(int(x1), int(y1), int(x2), int(y2))
        shape = self.predictor(gray, dlib_rect)

        coords = np.zeros((68, 2), dtype="float")
        for i in range(68):
            coords[i] = (shape.part(i).x, shape.part(i).y)
        return coords

    def _calculate_perclos(self):
        """Calculate PERCLOS (Percentage of Eye Closure) over time window"""
        if not self._eye_closure_history:
            return 0.0

        now = time.time()
        cutoff = now - self.perclos_window
        while self._eye_closure_history and self._eye_closure_history[0][0] < cutoff:
            self._eye_closure_history.popleft()

        if not self._eye_closure_history:
            return 0.0

        closed_count = sum(1 for _, closed in self._eye_closure_history if closed)
        return closed_count / len(self._eye_closure_history)

    def _calculate_yawns_per_minute(self):
        """Calculate yawn frequency over last minute"""
        now = time.time()
        cutoff = now - 60.0
        while self._yawn_history and self._yawn_history[0] < cutoff:
            self._yawn_history.popleft()
        return len(self._yawn_history)

    def _compute_fatigue_level(self, perclos, yawns_per_min):
        """Determine fatigue level based on metrics"""
        if perclos >= 0.4 or yawns_per_min >= self.yawn_threshold_severe:
            return "severe"
        elif perclos >= 0.25 or yawns_per_min >= self.yawn_threshold:
            return "mild"
        return "normal"

    def run(self):
        """Main processing loop"""
        cap = cv2.VideoCapture(self.camera_id)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        cap.set(cv2.CAP_PROP_FPS, self.fps)

        if not cap.isOpened():
            self.logger.error("Failed to open camera")
            return

        self.logger.info("Vision service started")

        try:
            while not (self.stop_event and self.stop_event.is_set()):
                ret, frame = cap.read()
                if not ret:
                    self.logger.warning("Failed to read frame")
                    time.sleep(0.1)
                    continue

                self._frame_count += 1

                # Frame skipping for performance
                if self._frame_count % self.frame_skip != 0:
                    time.sleep(0.01)  # Prevent tight loop
                    continue

                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

                # Detect faces
                if self.detection_method == "dnn":
                    faces = self._detect_faces_dnn(frame)
                else:
                    faces = self._detect_faces_haar(gray)

                if len(faces) == 0:
                    # No face detected
                    payload = {
                        "timestamp": time.time(),
                        "face_detected": False,
                        "fatigue_level": "normal",
                    }
                    self.publisher.publish("vision.metrics", payload)
                    time.sleep(0.05)
                    continue

                # Use largest face
                face = max(faces, key=lambda f: (f[2] - f[0]) * (f[3] - f[1]))

                # Get landmarks
                landmarks = self._get_landmarks(gray, face)
                if landmarks is None:
                    time.sleep(0.01)  # Prevent CPU spike when landmarks unavailable
                    continue

                # Extract eye and mouth regions
                left_eye = landmarks[42:48]
                right_eye = landmarks[36:42]
                mouth = landmarks[60:68]

                # Calculate metrics
                ear = (eye_aspect_ratio(left_eye) + eye_aspect_ratio(right_eye)) / 2.0
                mar = mouth_aspect_ratio(mouth)

                # Track eye closure
                is_closed = ear < self.ear_threshold
                self._eye_closure_history.append((time.time(), is_closed))

                if is_closed:
                    self._closed_eyes_counter += 1
                else:
                    if self._closed_eyes_counter >= self.ear_consec_frames:
                        self._blink_count += 1
                    self._closed_eyes_counter = 0

                # Track yawns
                if mar > self.mar_threshold:
                    self._yawn_history.append(time.time())

                # Calculate fatigue metrics
                perclos = self._calculate_perclos()
                yawns_per_min = self._calculate_yawns_per_minute()
                fatigue_level = self._compute_fatigue_level(perclos, yawns_per_min)

                # Publish metrics
                payload = {
                    "timestamp": time.time(),
                    "face_detected": True,
                    "fatigue_level": fatigue_level,
                    "ear": float(ear),
                    "mar": float(mar),
                    "perclos": float(perclos),
                    "yawns_per_min": float(yawns_per_min),
                    "blink_count": self._blink_count,
                }
                self.publisher.publish("vision.metrics", payload)

                time.sleep(0.01)

        except KeyboardInterrupt:
            self.logger.info("Vision service stopped by user")
        finally:
            cap.release()
            self.publisher.close()


if __name__ == "__main__":
    service = VisionService()
    service.run()
