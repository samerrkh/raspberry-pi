# gas_sensor.py
import logging
import time
import datetime
import pytz
import RPi.GPIO as GPIO
from firebase_admin import db

# Set up GPIO mode
GPIO.setmode(GPIO.BCM)
GPIO.setup(4, GPIO.IN, pull_up_down=GPIO.PUD_UP)

def send_gas_data_to_firebase(pi_serial, gas_status):
    try:
        utc_dt = datetime.datetime.now(datetime.timezone.utc)
        tz = pytz.timezone('Europe/Istanbul')
        gmt3_dt = utc_dt.astimezone(tz)
        formatted_time = gmt3_dt.strftime('%Y-%m-%d %H:%M:%S')

        gas_ref = db.reference(f'/sensor_data/{pi_serial}/gas-sensor')
        gas_data = gas_ref.get() or []
        gas_data.append({'timestamp': formatted_time, 'gas_detected': gas_status})

        if len(gas_data) > 15:
            gas_data.pop(0)

        gas_ref.set(gas_data)
    except Exception as e:
        logging.error(f"Error sending gas data to Firebase: {e}")

def read_gas_sensor():
    return not GPIO.input(4)  # Assuming active-low sensor
