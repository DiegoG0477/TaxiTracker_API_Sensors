import asyncio
import logging
import time
import json
import threading
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
import serial
import pynmea2
from statistics import mean, StatisticsError
from gpiozero import InputDevice
import smbus
from database.connector import DatabaseConnector
from services.rabbitmq_service import RabbitMQService
from driving.models import DrivingRequestModel
from crash.models import CrashRequestModel
from geolocation.controllers import get_kit_id, get_last_driver_id
from driving.controllers import register_driving_gpio
from crash.controllers import register_crash_gpio
from utils.travel_state import travel_state
from utils.current_driver import current_driver

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class GpioService:
    G_FORCE_THRESHOLD = 3.5
    DEBOUNCE_TIME = 100
    MAX_RETRIES = 6
    RETRY_DELAY = 0.1

    def __init__(self, gps_port="/dev/ttyAMA0", gps_baudrate=9600, gps_timeout=0.5):
        self.vibration_sw420 = InputDevice(17)
        self.shock_ky031 = InputDevice(27)
        self.bus = None
        self.Device_Address = 0x69
        self.initialize_i2c()
        self.start_time = self.millis()
        self.vibrations = 0
        self.shocks = 0
        self.last_shock_time = self.millis()
        self.data_buffer = []
        self.rabbitmq_service = RabbitMQService()
        self.database = DatabaseConnector()
        self.kit_id = None
        self.running = True
        self.current_coordinates = {'latitude': 0.0, 'longitude': 0.0}
        self.coordinates_valid = False
        self.ser = serial.Serial(gps_port, baudrate=gps_baudrate, timeout=gps_timeout)
        self.coordinates_lock = threading.Lock()
        self.executor = ThreadPoolExecutor(max_workers=2)  # For blocking IO operations

    async def start(self):
        try:
            self.sensor_thread = threading.Thread(target=self.read_sensors_loop)
            self.sensor_thread.start()
            self.gps_thread = threading.Thread(target=self.read_gps_data)
            self.gps_thread.start()
            await self.rabbitmq_service.connect()
            asyncio.create_task(self.process_and_send_data())
            self.kit_id = await get_kit_id()
            print("GPIO service started")
        except Exception as e:
            logger.error(f"Error starting integrated service: {e}")

    async def stop(self):
        self.running = False
        self.sensor_thread.join()
        self.gps_thread.join()
        self.ser.close()
        await self.rabbitmq_service.close_connection()
        print("GPIO service stopped")

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

    def read_sensors_loop(self):
        while self.running:
            sensor_data = self.read_sensors()
            if sensor_data:
                self.check_for_collision(sensor_data)
                self.data_buffer.append(sensor_data)
            time.sleep(1)

    def read_gps_data(self):
        while self.running:
            try:
                newdata = self.ser.readline().decode('ascii', errors='replace').strip()
                if newdata.startswith("$GPRMC"):
                    newmsg = pynmea2.parse(newdata)
                    if isinstance(newmsg, pynmea2.RMC):
                        if newmsg.status == 'A':
                            self.update_coordinates({'latitude': newmsg.latitude, 'longitude': newmsg.longitude})
                            self.coordinates_valid = True
                        else:
                            self.coordinates_valid = False
                time.sleep(1)
            except (serial.SerialException, pynmea2.ParseError, UnicodeDecodeError) as e:
                logger.error(f"Error reading GPS data: {e}")
                self.coordinates_valid = False

    def update_coordinates(self, new_coordinates):
        with self.coordinates_lock:
            self.current_coordinates = new_coordinates

    async def process_and_send_data(self):
        gps_counter = 0
        sensor_counter = 0
        while self.running:
            await asyncio.sleep(1)
            gps_counter += 1
            sensor_counter += 1

            if gps_counter == 3:
                await self.process_gps_data()
                gps_counter = 0

            if sensor_counter == 30:
                await self.process_sensor_data()
                sensor_counter = 0

    async def process_gps_data(self):
        try:
            coordinates = self.get_current_coordinates()
            if coordinates != "Coordinates not valid or sensor calibrating":
                lat = coordinates['latitude']
                lon = coordinates['longitude']
                coordinates_str = f"{lat},{lon}"
            else:
                coordinates_str = "..."

            if not travel_state.get_travel_status():
                driver_id = await get_last_driver_id()
            else:
                driver_id = current_driver.get_driver_id()

            message = json.dumps({
                "kit_id": self.kit_id,
                "driver_id": driver_id,
                "datetime": datetime.now().isoformat(),
                "coordinates": coordinates_str
            })

            if self.coordinates_valid:
                logger.info(f'Sending coordinates: {message}')
                point = f"POINT({coordinates['latitude']} {coordinates['longitude']})"
                await self.database.query_post(
                    "INSERT INTO geolocation (coordinates, geo_time) VALUES (ST_GeomFromText(%s), %s)",
                    (point, datetime.now())
                )
                await self.rabbitmq_service.send_message(message, "geolocation.update")
            else:
                logger.info("GPS coordinates are not valid or sensor is calibrating.")
                await self.rabbitmq_service.send_message(json.dumps({
                    "kit_id": self.kit_id,
                    "driver_id": driver_id,
                    "datetime": datetime.now().isoformat(),
                    "coordinates": "..."
                }), "geolocation.status")
        except Exception as e:
            logger.error(f"Error processing GPS data: {e}")

    async def process_sensor_data(self):
        avg_data = self.calculate_averages()
        if avg_data:
            await self.send_driving_data(avg_data)
        self.data_buffer = []  # Clear the buffer after sending data

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
    
    async def get_current_coordinates_async(self):
        result = await asyncio.to_thread(self.get_current_coordinates)
        return result

    def check_for_collision(self, sensor_data):
        if abs(sensor_data['g_force_x']) > self.G_FORCE_THRESHOLD or abs(sensor_data['g_force_y']) > self.G_FORCE_THRESHOLD:
            logger.warning(f"High G-force detected: X={sensor_data['g_force_x']}g, Y={sensor_data['g_force_y']}g")
            self.send_crash_alert(sensor_data)

    def calculate_g_force(self, ax, ay, az):
        return round((ax ** 2 + ay ** 2 + az ** 2) ** 0.5, 2)

    def calculate_averages(self):
        try:
            avg_acc_x = round(mean([data['acc_x'] for data in self.data_buffer]), 2)
            avg_acc_y = round(mean([data['acc_y'] for data in self.data_buffer]), 2)
            avg_acc_z = round(mean([data['acc_z'] for data in self.data_buffer]), 2)
            avg_gyro_x = round(mean([data['gyro_x'] for data in self.data_buffer]), 2)
            avg_gyro_y = round(mean([data['gyro_y'] for data in self.data_buffer]), 2)
            avg_gyro_z = round(mean([data['gyro_z'] for data in self.data_buffer]), 2)
            avg_angle = round(mean([data['angle'] for data in self.data_buffer]), 2)
            avg_g_force = round(mean([data['g_force'] for data in self.data_buffer]), 2)

            return {
                'avg_acc_x': avg_acc_x, 'avg_acc_y': avg_acc_y, 'avg_acc_z': avg_acc_z,
                'avg_gyro_x': avg_gyro_x, 'avg_gyro_y': avg_gyro_y, 'avg_gyro_z': avg_gyro_z,
                'avg_angle': avg_angle, 'avg_g_force': avg_g_force,
                'vibrations': self.vibrations, 'shocks': self.shocks
            }
        except StatisticsError as e:
            logger.error(f"Error calculating averages: {e}")
            return None

    async def send_driving_data(self, avg_data):
        try:
            driving_request = DrivingRequestModel(
                kit_id=self.kit_id,
                avg_acc_x=avg_data['avg_acc_x'], avg_acc_y=avg_data['avg_acc_y'], avg_acc_z=avg_data['avg_acc_z'],
                avg_gyro_x=avg_data['avg_gyro_x'], avg_gyro_y=avg_data['avg_gyro_y'], avg_gyro_z=avg_data['avg_gyro_z'],
                avg_angle=avg_data['avg_angle'], avg_g_force=avg_data['avg_g_force'],
                vibrations=self.vibrations, shocks=self.shocks,
                datetime=datetime.now().isoformat()
            )
            await register_driving_gpio(driving_request)
        except Exception as e:
            logger.error(f"Error sending driving data: {e}")

    def send_crash_alert(self, sensor_data):
        try:
            crash_request = CrashRequestModel(
                kit_id=self.kit_id,
                g_force_x=sensor_data['g_force_x'], g_force_y=sensor_data['g_force_y'],
                g_force=sensor_data['g_force'],
                datetime=datetime.now().isoformat()
            )
            asyncio.run(register_crash_gpio(crash_request))
        except Exception as e:
            logger.error(f"Error sending crash alert: {e}")

    def get_current_coordinates(self):
        with self.coordinates_lock:
            if self.coordinates_valid:
                return self.current_coordinates
            else:
                return "Coordinates not valid or sensor calibrating"

    def MPU_Init(self):
        self.bus.write_byte_data(self.Device_Address, 0x19, 7)
        self.bus.write_byte_data(self.Device_Address, 0x6B, 1)
        self.bus.write_byte_data(self.Device_Address, 0x1A, 0)
        self.bus.write_byte_data(self.Device_Address, 0x1B, 24)
        self.bus.write_byte_data(self.Device_Address, 0x38, 1)

    def read_raw_data(self, addr):
        high = self.bus.read_byte_data(self.Device_Address, addr)
        low = self.bus.read_byte_data(self.Device_Address, addr + 1)
        value = ((high << 8) | low)
        if value > 32768:
            value = value - 65536
        return value

    def millis(self):
        return int(round(time.time() * 1000))

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

# Crear instancia del servicio
gpio_service = GpioService()