import time
from datetime import datetime
from gpiozero import InputDevice
import smbus
import logging
import requests
from statistics import mean

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SensorReader:
    G_FORCE_THRESHOLD = 3.5
    DEBOUNCE_TIME = 100
    MAX_RETRIES = 6
    RETRY_DELAY = 0.1
    DRIVING_URL = "http://localhost:8000/driving"
    CRASH_URL = "http://localhost:8000/crashes"

    def __init__(self):
        # Vibration and shock sensor configuration
        self.vibration_sw420 = InputDevice(17)
        self.shock_ky031 = InputDevice(27)

        # MPU6050 configuration
        self.bus = None
        self.Device_Address = 0x69
        self.initialize_i2c()

        # Vibration and shock variables
        self.start_time = self.millis()
        self.vibrations = 0
        self.shocks = 0
        self.last_shock_time = self.millis()

        # Buffer for 30-second data
        self.data_buffer = []

    def initialize_i2c(self):
        retry_count = 0
        while retry_count < self.MAX_RETRIES:
            try:
                self.bus = smbus.SMBus(1)
                self.MPU_Init()
                logger.info("I2C bus initialized successfully")
                break
            except OSError as e:
                logger.error(f"Error initializing I2C bus (attempt {retry_count + 1}): {e}")
                retry_count += 1
                time.sleep(self.RETRY_DELAY)
        
        if retry_count == self.MAX_RETRIES:
            logger.error("Failed to initialize I2C bus after multiple attempts")
        else:
            logger.info("I2C initialization complete")

    def read_sensors(self):
        retry_count = 0
        while retry_count < self.MAX_RETRIES:
            try:
                acc_x = self.read_raw_data(self.ACCEL_XOUT)
                acc_y = self.read_raw_data(self.ACCEL_YOUT)
                acc_z = self.read_raw_data(self.ACCEL_ZOUT)
                gyro_x = self.read_raw_data(self.GYRO_XOUT)
                gyro_y = self.read_raw_data(self.GYRO_YOUT)
                gyro_z = self.read_raw_data(self.GYRO_ZOUT)

                Ax = round(acc_x / 16384.0, 2)
                Ay = round(acc_y / 16384.0, 2)
                Az = round(acc_z / 16384.0, 2)
                Axms = round(Ax * 9.81, 2)
                Ayms = round(Ay * 9.81, 2)
                Azms = round(Az * 9.81, 2)
                Gx = round(gyro_x / 131.0, 2)
                Gy = round(gyro_y / 131.0, 2)
                Gz = round(gyro_z / 131.0, 2)

                if self.vibration_sw420.is_active:
                    self.vibrations += 1
                if self.shock_ky031.is_active:
                    current_time = self.millis()
                    if current_time - self.last_shock_time > self.DEBOUNCE_TIME:
                        self.shocks += 1
                        self.last_shock_time = current_time

                angle = (Ay - 1) * 180 / (-2) + 0
                angle = int(angle)

                return {
                    'acc_x': Axms, 'acc_y': Ayms, 'acc_z': Azms,
                    'gyro_x': Gx, 'gyro_y': Gy, 'gyro_z': Gz,
                    'angle': angle,
                    'vibrations': self.vibrations,
                    'shocks': self.shocks,
                    'g_force_x': Ax,
                    'g_force_y': Ay,
                    'g_force': self.calculate_g_force(Ax, Ay, Az)
                }
            except OSError as e:
                logger.error(f"Error reading sensors (attempt {retry_count + 1}): {e}")
                retry_count += 1
                time.sleep(self.RETRY_DELAY)
                if retry_count == self.MAX_RETRIES:
                    logger.error("Failed to read sensors after multiple attempts")
                    return None
                self.initialize_i2c()
    
    def read_raw_data(self, addr):
        retry_count = 0
        while retry_count < self.MAX_RETRIES:
            try:
                high = self.bus.read_byte_data(self.Device_Address, addr)
                low = self.bus.read_byte_data(self.Device_Address, addr + 1)
                value = ((high << 8) | low)
                if value > 32768:
                    value = value - 65536
                return value
            except OSError as e:
                logger.error(f"Error reading raw data (attempt {retry_count + 1}): {e}")
                retry_count += 1
                time.sleep(self.RETRY_DELAY)
                if retry_count == self.MAX_RETRIES:
                    logger.error(f"Failed to read raw data from address {addr} after multiple attempts")
                    return 0
                self.initialize_i2c()

    def calculate_averages(self):
        if not self.data_buffer:
            return None

        avg_data = {
            "acceleration": mean([d['acc_x'] for d in self.data_buffer if d['acc_x'] > 0]),
            "deceleration": abs(mean([d['acc_x'] for d in self.data_buffer if d['acc_x'] < 0])),
            "vibrations": sum(d['vibrations'] for d in self.data_buffer),
            "inclination_angle": mean(d['angle'] for d in self.data_buffer),
            "angular_velocity": mean(d['gyro_x'] for d in self.data_buffer),
            "g_force_x": mean(d['g_force_x'] for d in self.data_buffer),
            "g_force_y": mean(d['g_force_y'] for d in self.data_buffer)
        }
        return avg_data

    def send_driving_data(self, data):
        payload = {
            "datetime": datetime.now().isoformat(),
            "acceleration": data['acceleration'],
            "deceleration": data['deceleration'],
            "vibrations": data['vibrations'],
            "inclination_angle": data['inclination_angle'],
            "angular_velocity": data['angular_velocity'],
            "g_force_x": data['g_force_x'],
            "g_force_y": data['g_force_y']
        }
        try:
            response = requests.post(self.DRIVING_URL, json=payload)
            response.raise_for_status()
            logger.info("Driving data sent successfully")
        except requests.RequestException as e:
            logger.error(f"Error sending driving data: {e}")

    def millis(self):
        return int(round(time.time() * 1000))

    def calculate_g_force(self, x, y, z):
        return (x ** 2 + y ** 2 + z ** 2) ** 0.5

    def check_for_collision(self, data):
        if data['g_force'] > self.G_FORCE_THRESHOLD:
            logger.warning("Collision detected!")
            self.send_crash_alert(data)

    def send_crash_alert(self, data):
        payload = {
            "datetime": datetime.now().isoformat(),
            "impact_force": data['g_force'],
        }

        try:
            response = requests.post(self.CRASH_URL, json=payload)
            response.raise_for_status()
            logger.info("Crash data sent successfully")
        except requests.RequestException as e:
            logger.error(f"Error sending crash data: {e}")

    def MPU_Init(self):
        logger.info("Initializing MPU6050...")
        self.bus.write_byte_data(self.Device_Address, self.SMPLRT_DIV, 7)
        self.bus.write_byte_data(self.Device_Address, self.PWR_MGMT_1, 1)
        self.bus.write_byte_data(self.Device_Address, self.CONFIG, 0)
        self.bus.write_byte_data(self.Device_Address, self.GYRO_CONFIG, 24)
        self.bus.write_byte_data(self.Device_Address, self.INT_ENABLE, 1)
        logger.info("MPU6050 initialized")

    # MPU6050 Registers and their addresses
    PWR_MGMT_1 = 0x6B
    SMPLRT_DIV = 0x19
    CONFIG = 0x1A
    GYRO_CONFIG = 0x1B
    INT_ENABLE = 0x38
    ACCEL_XOUT = 0x3B
    ACCEL_YOUT = 0x3D
    ACCEL_ZOUT = 0x3F
    GYRO_XOUT = 0x43
    GYRO_YOUT = 0x45
    GYRO_ZOUT = 0x47

def main():
    sensor_reader = SensorReader()
    logger.info("Starting sensor readings...")
    
    try:
        while True:
            start_time = time.time()
            while time.time() - start_time < 30:
                sensor_data = sensor_reader.read_sensors()
                if sensor_data:
                    logger.info(f"Sensor data: {sensor_data}")
                    sensor_reader.check_for_collision(sensor_data)
                    sensor_reader.data_buffer.append(sensor_data)
                time.sleep(1)
            
            avg_data = sensor_reader.calculate_averages()
            if avg_data:
                sensor_reader.send_driving_data(avg_data)
            sensor_reader.data_buffer = []  # Clear the buffer after sending data
    except KeyboardInterrupt:
        logger.info("Sensor readings stopped by user.")

if __name__ == "__main__":
    main()