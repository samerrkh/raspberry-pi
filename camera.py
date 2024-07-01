import logging
import time
from io import BytesIO
from threading import Lock, Event
from picamera2 import Picamera2
from picamera2.encoders import JpegEncoder

# Initialize logging
logging.basicConfig(level=logging.DEBUG)

# Suppress picamera2 logs
logging.getLogger("picamera2").setLevel(logging.WARNING)

# Camera setup
camera_lock = Lock()
camera_instance = None
pause_cry_detection = Event()

def initialize_camera():
    global camera_instance
    if camera_instance is None:
        camera_instance = Picamera2()
        camera_instance.configure(camera_instance.create_video_configuration(main={"size": (640, 480)}))
        camera_instance.start()
    return camera_instance

def release_camera():
    global camera_instance
    if camera_instance:
        try:
            camera_instance.stop()
            camera_instance.close()
            camera_instance = None
        except Exception as e:
            logging.error(f"Error releasing camera: {e}")

def gen_frames():
    stream = BytesIO()
    encoder = JpegEncoder()

    try:
        with camera_lock:
            initialize_camera()

        # Pause cry detection
        pause_cry_detection.set()

        while True:
            with camera_lock:
                stream.seek(0)
                stream.truncate()  # Clear the stream before capturing new frame
                camera_instance.capture_file(stream, format="jpeg")
                frame = stream.getvalue()
                if frame:
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
            time.sleep(0.1)  # Add a small delay to reduce CPU usage and avoid overloading the camera
    except Exception as e:
        logging.error(f"Error capturing frame: {e}")
    finally:
        with camera_lock:
            release_camera()
        
        # Resume cry detection
        pause_cry_detection.clear()
