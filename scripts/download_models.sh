#!/bin/bash
# Download required AI models

set -e

echo "Downloading AI models..."

# Create models directory
mkdir -p models
cd models

# Download dlib face landmark predictor
if [ ! -f "shape_predictor_68_face_landmarks.dat" ]; then
    echo "Downloading dlib 68-point face landmark model..."
    wget -q --show-progress \
        http://dlib.net/files/shape_predictor_68_face_landmarks.dat.bz2
    bzip2 -d shape_predictor_68_face_landmarks.dat.bz2
    echo "✓ dlib landmark model downloaded"
else
    echo "✓ dlib landmark model already exists"
fi

# Download OpenCV DNN face detection model
if [ ! -f "deploy.prototxt" ] || [ ! -f "res10_300x300_ssd_iter_140000.caffemodel" ]; then
    echo "Downloading OpenCV DNN face detection model..."
    wget -q --show-progress \
        https://raw.githubusercontent.com/opencv/opencv/master/samples/dnn/face_detector/deploy.prototxt
    wget -q --show-progress \
        https://raw.githubusercontent.com/opencv/opencv_3rdparty/dnn_samples_face_detector_20170830/res10_300x300_ssd_iter_140000.caffemodel
    echo "✓ OpenCV DNN model downloaded"
else
    echo "✓ OpenCV DNN model already exists"
fi

# Download Vosk speech recognition model
if [ ! -d "vosk-model-small-en-us-0.15" ]; then
    echo "Downloading Vosk speech recognition model (this may take a while)..."
    wget -q --show-progress \
        https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip
    unzip -q vosk-model-small-en-us-0.15.zip
    rm vosk-model-small-en-us-0.15.zip
    echo "✓ Vosk model downloaded"
else
    echo "✓ Vosk model already exists"
fi

cd ..

echo ""
echo "All models downloaded successfully!"
echo ""
echo "Note: Porcupine wake word models need to be generated from"
echo "      https://console.picovoice.ai/ and configured in config.yaml"
echo ""
