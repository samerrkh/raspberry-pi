from flask import Flask, request, jsonify, Response
from flask_cors import CORS
import logging
from io import BytesIO
from threading import Lock, Thread
import time
import datetime
import pytz
import smbus2 as smbus
import RPi.GPIO as GPIO
import firebase_admin
from firebase_admin import credentials, db
from picamera2 import Picamera2
from picamera2.encoders import JpegEncoder
import os

# Initialize logging
logging.basicConfig(level=logging.DEBUG)

# Initialize Firebase
def get_raspberry_pi_serial_number():
    try:
        with open('/proc/cpuinfo', 'r') as f:
            for line in f:
                if line.startswith('Serial'):
                    return line.split(':')[1].strip()
    except Exception as e:
        logging.error(f"Failed to get Raspberry Pi serial number: {e}")
        return '1000000062ee9c4c'

cred = credentials.Certificate('/home/pi/Desktop/peaceful-cradle-project/peaceful-cradle-firebase-adminsdk-e3cnu-3faca0b901.json')
firebase_admin.initialize_app(cred, {
    'databaseURL': 'https://peaceful-cradle-default-rtdb.firebaseio.com'
})

# Setup for SMBus (I2C)
i2c = smbus.SMBus(1)
addr = 0x44
i2c.write_byte_data(addr, 0x23, 0x34)
time.sleep(0.5)

def read_sensor_data():
    try:
        i2c.write_byte_data(addr, 0xE0, 0x00)
        data = i2c.read_i2c_block_data(addr, 0x00, 6)
        rawT = (data[0] << 8) | data[1]
        rawR = (data[3] << 8) | data[4]
        temperature = -45 + (175 * rawT / 65535)
        humidity = 100 * rawR / 65535
        return {'temperature': temperature, 'humidity': humidity}
    except Exception as e:
        logging.error(f"Error reading sensor data: {e}")
        return {'temperature': None, 'humidity': None}

def send_data_to_firebase(pi_serial, sensor_data, gas_status, update_gas_only=False):
    try:
        utc_dt = datetime.datetime.now(datetime.timezone.utc)
        tz = pytz.timezone('Europe/Istanbul')
        gmt3_dt = utc_dt.astimezone(tz)
        formatted_time = gmt3_dt.strftime('%Y-%m-%d %H:%M:%S')

        if not update_gas_only:
            sensor_data['timestamp'] = formatted_time
            ref = db.reference(f'/sensor_data/{pi_serial}/tempAndHumidity')
            ref.set(sensor_data)

        gas_ref = db.reference(f'/sensor_data/{pi_serial}/gas-sensor')
        gas_data = gas_ref.get() or []
        gas_data.append({'timestamp': formatted_time, 'gas_detected': gas_status})

        if len(gas_data) > 15:
            gas_data.pop(0)

        gas_ref.set(gas_data)
    except Exception as e:
        logging.error(f"Error sending data to Firebase: {e}")

# Set up GPIO mode
GPIO.setmode(GPIO.BCM)
GPIO.setup(4, GPIO.IN, pull_up_down=GPIO.PUD_UP)

pi_serial = get_raspberry_pi_serial_number()

# Flask server setup
app = Flask(__name__)
CORS(app)

vlc_host = '127.0.0.1'
vlc_port = 4212

camera_lock = Lock()

def initialize_camera():
    camera_instance = Picamera2()
    camera_instance.configure(camera_instance.create_video_configuration(main={"size": (640, 480)}))
    camera_instance.start()
    return camera_instance

def gen_frames():
    logging.debug("Starting video capture")
    stream = BytesIO()
    encoder = JpegEncoder()
    camera_instance = None

    try:
        with camera_lock:
            camera_instance = initialize_camera()

        while True:
            with camera_lock:
                stream.seek(0)
                stream.truncate()  # Clear the stream before capturing new frame
                camera_instance.capture_file(stream, format="jpeg")
                frame = stream.getvalue()
                if frame:
                    logging.debug(f"Captured frame of size: {len(frame)}")
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
                else:
                    logging.warning("Empty frame captured")
    except Exception as e:
        logging.error(f"Error capturing frame: {e}")
    finally:
        if camera_instance:
            with camera_lock:
                try:
                    camera_instance.stop()
                    camera_instance.close()  # Ensure camera is properly closed
                except Exception as e:
                    logging.error(f"Error stopping camera: {e}")
        time.sleep(2)  # Add a small delay to ensure hardware reset

@app.route('/video_feed')
def video_feed():
    logging.debug("Video feed endpoint called")
    return Response(gen_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/play', methods=['POST'])
def play_song():
    data = request.json
    song = data.get('song')
    volume = data.get('volume', 0.5)
    loop = data.get('loop', False)
    logging.debug(f"Received request to play song: {song} at volume: {volume} with loop: {loop}")
    if not os.path.exists(f"/home/pi/Downloads/{song}.mp3"):
        logging.error(f"Error: File /home/pi/Downloads/{song}.mp3 does not exist")
        return jsonify({"error": "File does not exist"}), 404
    os.system(f"pkill vlc")
    play_command = f"cvlc --gain {int(volume * 256)} /home/pi/Downloads/{song}.mp3 --extraintf rc --rc-host {vlc_host}:{vlc_port} {'--loop' if loop else ''} &"
    logging.debug(f"Executing command: {play_command}")
    os.system(play_command)
    return jsonify({"message": f"Playing {song} at volume {volume}"}), 200

@app.route('/toggle', methods=['POST'])
def toggle_play():
    logging.debug("Received request to toggle play/pause")
    response = send_command_to_vlc("pause")
    logging.debug(f"VLC response: {response}")
    return jsonify({"message": "Toggled play/pause"}), 200

@app.route('/volume', methods=['POST'])
def adjust_volume():
    data = request.json
    volume = data.get('volume', 0.5)
    logging.debug(f"Received request to adjust volume to: {volume}")
    response = send_command_to_vlc(f"volume {int(volume * 256)}")
    logging.debug(f"VLC response: {response}")
    return jsonify({"message": f"Volume set to {volume}"}), 200

@app.route('/seek', methods=['POST'])
def seek():
    data = request.json
    position = data.get('position', 0.0)
    logging.debug(f"Received request to seek to position: {position}")
    response = send_command_to_vlc(f"seek {position}")
    logging.debug(f"VLC response: {response}")
    return jsonify({"message": f"Seeked to {position}"}), 200

@app.route('/loop', methods=['POST'])
def set_loop():
    data = request.json
    loop = data.get('loop', False)
    logging.debug(f"Received request to set loop: {loop}")
    command = "loop on" if loop else "loop off"
    response = send_command_to_vlc(command)
    logging.debug(f"VLC response: {response}")
    return jsonify({"message": f"Loop set to {loop}"}), 200

@app.route('/status', methods=['GET'])
def get_status():
    logging.debug("Received request to get VLC status")
    response = send_command_to_vlc("status")
    logging.debug(f"VLC response: {response}")
    return jsonify({"status": response}), 200

def sensor_data_loop():
    last_temp_humidity_update = time.time()

    try:
        while True:
            current_time = time.time()

            # Read the input from the gas sensor
            gas_detected = not GPIO.input(4)  # Assuming active-low sensor
            gas_status = "Gas detected!!" if gas_detected else "No gas detected."

            # Send gas sensor data to Firebase every 3 seconds
            send_data_to_firebase(pi_serial, {}, gas_status, update_gas_only=True)

            # Send temperature and humidity data to Firebase every 20 seconds
            if current_time - last_temp_humidity_update >= 20:
                sensor_data = read_sensor_data()
                send_data_to_firebase(pi_serial, sensor_data, gas_status, update_gas_only=False)
                last_temp_humidity_update = current_time

            time.sleep(3)  # Gas sensor data sent every 3 seconds

    finally:
        logging.debug("Cleaning up GPIO")
        GPIO.cleanup()

if __name__ == '__main__':
    # Start sensor data loop in a separate thread
    sensor_thread = Thread(target=sensor_data_loop)
    sensor_thread.start()

    # Run the Flask app
    logging.debug("Starting Flask server")
    app.run(host='0.0.0.0', port=5000)
