import firebase_admin
import time
import datetime
import pytz
import smbus2 as smbus
from firebase_admin import db, credentials, initialize_app
import RPi.GPIO as GPIO
from flask import Flask, request, jsonify
import os
from threading import Thread
import socket

# Initialize Firebase
def get_raspberry_pi_serial_number():
    try:
        with open('/proc/cpuinfo', 'r') as f:
            for line in f:
                if line.startswith('Serial'):
                    return line.split(':')[1].strip()
    except:
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
    i2c.write_byte_data(addr, 0xE0, 0x00)
    data = i2c.read_i2c_block_data(addr, 0x00, 6)
    rawT = (data[0] << 8) | data[1]
    rawR = (data[3] << 8) | data[4]
    temperature = -45 + (175 * rawT / 65535)
    humidity = 100 * rawR / 65535
    return {'temperature': temperature, 'humidity': humidity}

def send_data_to_firebase(pi_serial, sensor_data, gas_status, update_gas_only=False):
    # Create a timezone-aware datetime object for UTC
    utc_dt = datetime.datetime.now(datetime.timezone.utc)

    # Convert to GMT+3 using pytz
    tz = pytz.timezone('Europe/Istanbul')  # Using Istanbul as it is in GMT+3
    gmt3_dt = utc_dt.astimezone(tz)

    # Format the datetime to 'YYYY-MM-DD HH:MM:SS'
    formatted_time = gmt3_dt.strftime('%Y-%m-%d %H:%M:%S')

    if not update_gas_only:
        sensor_data['timestamp'] = formatted_time
        # Update temperature and humidity
        ref = db.reference(f'/sensor_data/{pi_serial}/tempAndHumidity')
        ref.set(sensor_data)  # This will overwrite the existing data

    # Update gas sensor data in a rolling window fashion
    gas_ref = db.reference(f'/sensor_data/{pi_serial}/gas-sensor')
    gas_data = gas_ref.get() or []
    gas_data.append({'timestamp': formatted_time, 'gas_detected': gas_status})

    if len(gas_data) > 15:
        gas_data.pop(0)

    gas_ref.set(gas_data)

# Set up GPIO mode
GPIO.setmode(GPIO.BCM)
# Set up GPIO 4 as an input with an internal pull-up resistor
GPIO.setup(4, GPIO.IN, pull_up_down=GPIO.PUD_UP)

pi_serial = get_raspberry_pi_serial_number()

# Flask server setup
app = Flask(__name__)

vlc_host = '127.0.0.1'
vlc_port = 4212

def send_command_to_vlc(command):
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((vlc_host, vlc_port))
        sock.sendall(f"{command}\n".encode('utf-8'))
        response = sock.recv(1024).decode('utf-8')
        sock.close()
        print(f"Command: {command}, Response: {response}")
        return response
    except Exception as e:
        print(f"Error sending command to VLC: {e}")
        return None

@app.route('/play', methods=['POST'])
def play_song():
    data = request.json
    song = data.get('song')
    volume = data.get('volume', 0.5)
    loop = data.get('loop', False)
    print(f"Received request to play song: {song} at volume: {volume} with loop: {loop}")
    if not os.path.exists(f"/home/pi/Downloads/{song}.mp3"):
        print(f"Error: File /home/pi/Downloads/{song}.mp3 does not exist")
        return jsonify({"error": "File does not exist"}), 404
    os.system(f"pkill vlc")  # Kill any existing VLC instances
    play_command = f"cvlc --gain {int(volume * 256)} /home/pi/Downloads/{song}.mp3 --extraintf rc --rc-host {vlc_host}:{vlc_port} {'--loop' if loop else ''} &"
    print(f"Executing command: {play_command}")
    os.system(play_command)
    return jsonify({"message": f"Playing {song} at volume {volume}"}), 200

@app.route('/toggle', methods=['POST'])
def toggle_play():
    print("Received request to toggle play/pause")
    response = send_command_to_vlc("pause")
    print(f"VLC response: {response}")
    return jsonify({"message": "Toggled play/pause"}), 200

@app.route('/volume', methods=['POST'])
def adjust_volume():
    data = request.json
    volume = data.get('volume', 0.5)
    print(f"Received request to adjust volume to: {volume}")
    response = send_command_to_vlc(f"volume {int(volume * 256)}")
    print(f"VLC response: {response}")
    return jsonify({"message": f"Volume set to {volume}"}), 200

@app.route('/seek', methods=['POST'])
def seek():
    data = request.json
    position = data.get('position', 0.0)
    print(f"Received request to seek to position: {position}")
    response = send_command_to_vlc(f"seek {position}")
    print(f"VLC response: {response}")
    return jsonify({"message": f"Seeked to {position}"}), 200

@app.route('/loop', methods=['POST'])
def set_loop():
    data = request.json
    loop = data.get('loop', False)
    print(f"Received request to set loop: {loop}")
    command = "loop on" if loop else "loop off"
    response = send_command_to_vlc(command)
    print(f"VLC response: {response}")
    return jsonify({"message": f"Loop set to {loop}"}), 200

@app.route('/status', methods=['GET'])
def get_status():
    print("Received request to get VLC status")
    response = send_command_to_vlc("status")
    print(f"VLC response: {response}")
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
        print("Cleaning up...")
        GPIO.cleanup()

if __name__ == '__main__':
    # Start sensor data loop in a separate thread
    sensor_thread = Thread(target=sensor_data_loop)
    sensor_thread.start()

    # Run the Flask app
    print("Starting Flask server...")
    app.run(host='0.0.0.0', port=5000)
