from flask import Flask, request, jsonify, Response
from flask_cors import CORS
import logging
from threading import Thread, Event
import time
import os
import signal
import asyncio
import firebase_admin
from firebase_admin import credentials
import temperature_humidity
import gas_sensor
import camera
import audio_stream
from vlc_control import send_command_to_vlc
import baby_cry_detection

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

cred = credentials.Certificate('/home/pi/Desktop/peaceful-cradle-project/peaceful-cradle-firebase-adminsdk-e3cnu-c11828e788.json')
firebase_admin.initialize_app(cred, {
    'databaseURL': 'https://peaceful-cradle-default-rtdb.firebaseio.com'
})

pi_serial = get_raspberry_pi_serial_number()

# Set environment variables for the baby_cry_detection script
os.environ['PI_SERIAL'] = pi_serial

# Flask server setup
app = Flask(__name__)
CORS(app)

# Global variable to manage cry detection state
video_stream_active = Event()
shutdown_event = Event()

@app.route('/video_feed')
def video_feed():
    logging.debug("Video feed endpoint called")
    video_stream_active.set()  # Indicate that video streaming is active
    try:
        return Response(camera.gen_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')
    except Exception as e:
        logging.error(f"Error in video feed: {e}")
        return "Video feed error", 500

@app.route('/stop_video_feed')
def stop_video_feed():
    logging.debug("Stop video feed endpoint called")
    video_stream_active.clear()  # Indicate that video streaming has stopped
    return "Video feed stopped", 200

@app.route('/test_connection')
def test_connection():
    logging.debug("Test connection endpoint called")
    return "Connection successful", 200

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
    play_command = f"cvlc --gain {int(volume * 256)} /home/pi/Downloads/{song}.mp3 --extraintf rc --rc-host 127.0.0.1:4212 {'--loop' if loop else ''} &"
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
        while not shutdown_event.is_set():
            current_time = time.time()

            # Read the input from the gas sensor
            gas_detected = gas_sensor.read_gas_sensor()
            gas_status = "Gas detected!!" if gas_detected else "No gas detected."

            # Send gas sensor data to Firebase every 3 seconds
            gas_sensor.send_gas_data_to_firebase(pi_serial, gas_status)

            # Send temperature and humidity data to Firebase every 20 seconds
            if current_time - last_temp_humidity_update >= 20:
                sensor_data = temperature_humidity.read_sensor_data()
                temperature_humidity.send_temperature_humidity_to_firebase(pi_serial, sensor_data)
                last_temp_humidity_update = current_time

            time.sleep(3)  # Gas sensor data sent every 3 seconds

    finally:
        logging.debug("Cleaning up GPIO")
        GPIO.cleanup()

def cry_detection_loop():
    while not shutdown_event.is_set():
        if not video_stream_active.is_set():
            baby_cry_detection.start_listening()
        else:
            time.sleep(1)  # Sleep for a while if video stream is active

def signal_handler(sig, frame):
    logging.info("Signal received, shutting down...")
    shutdown_event.set()
    video_stream_active.clear()
    os._exit(0)

if __name__ == '__main__':
    # Register signal handlers for clean shutdown
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Start sensor data loop in a separate thread
    sensor_thread = Thread(target=sensor_data_loop)
    sensor_thread.start()

    # Start baby cry detection in a separate thread
    logging.debug("Starting baby cry detection thread")
    cry_detection_thread = Thread(target=cry_detection_loop)
    cry_detection_thread.start()

    # Start the video stream in a separate thread
    logging.debug("Starting video stream")
    video_thread = Thread(target=camera.initialize_camera)
    video_thread.start()

    # Start the audio streams
    logging.debug("Starting audio streams")
    audio_thread = Thread(target=lambda: asyncio.run(audio_stream.start_audio_servers()))
    audio_thread.start()

    # Run the Flask app
    logging.debug("Starting Flask server")
    app.run(host='0.0.0.0', port=5000)

    # Ensure threads are terminated when main process exits
    sensor_thread.join()
    cry_detection_thread.join()
    video_thread.join()
    audio_thread.join()
