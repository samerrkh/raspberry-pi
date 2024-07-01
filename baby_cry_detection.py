import logging
import time
import numpy as np
import pyaudio
import firebase_admin
from firebase_admin import db
from threading import Event
import os

# Initialize logging
logging.basicConfig(level=logging.DEBUG)

# Get Pi serial number from environment variable
pi_serial = os.getenv('PI_SERIAL', '1000000062ee9c4c')

# Pause event from camera
from camera import pause_cry_detection

def send_cry_detection_to_firebase(detected):
    ref = db.reference(f'/sensor_data/{pi_serial}/cry_detection')
    ref.set({
        'detected': detected,
        'timestamp': int(time.time())
    })
    logging.debug(f"Sent cry detection status to Firebase: {detected}")

def calculate_decibels(audio_data):
    rms = np.sqrt(np.mean(np.square(audio_data)))
    if rms == 0:
        return 0
    db = 20 * np.log10(rms)
    return db

def detect_baby_cry(audio_data):
    db = calculate_decibels(audio_data)
    logging.debug(f"Detected sound level: {db:.2f} dB")
    return 10 <= db <= 120

def start_listening():
    p = pyaudio.PyAudio()
    stream = p.open(format=pyaudio.paInt16, channels=1, rate=44100, input=True, frames_per_buffer=1024)

    logging.debug("Listening for baby cries...")

    try:
        while True:
            # Check if cry detection is paused
            if pause_cry_detection.is_set():
                logging.debug("Cry detection paused")
                time.sleep(1)
                continue

            data = stream.read(1024)
            audio_data = np.frombuffer(data, dtype=np.int16)

            if detect_baby_cry(audio_data):
                logging.debug("Baby cry detected!")
                send_cry_detection_to_firebase(True)
            else:
                send_cry_detection_to_firebase(False)

    except KeyboardInterrupt:
        logging.debug("Stopping...")
    finally:
        stream.stop_stream()
        stream.close()
        p.terminate()
