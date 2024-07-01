# temperature_humidity.py
import logging
import time
import datetime
import pytz
import smbus2 as smbus
from firebase_admin import db

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

def send_temperature_humidity_to_firebase(pi_serial, sensor_data):
    try:
        utc_dt = datetime.datetime.now(datetime.timezone.utc)
        tz = pytz.timezone('Europe/Istanbul')
        gmt3_dt = utc_dt.astimezone(tz)
        formatted_time = gmt3_dt.strftime('%Y-%m-%d %H:%M:%S')

        sensor_data['timestamp'] = formatted_time
        ref = db.reference(f'/sensor_data/{pi_serial}/tempAndHumidity')
        ref.set(sensor_data)
    except Exception as e:
        logging.error(f"Error sending temperature and humidity data to Firebase: {e}")
