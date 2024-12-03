import asyncio
import logging
import time
from datetime import datetime
import json
import threading
import serial
import pynmea2
from gpiozero import InputDevice
from statistics import mean, StatisticsError
import smbus
from database.connector import DatabaseConnector
from services.rabbitmq_service import RabbitMQService
from driving.models import DrivingRequestModel
from crash.models import CrashRequestModel
from geolocation.controllers import get_kit_id, get_last_driver_id
from driving.controllers import driving_controller
from crash.controllers import crash_controller
from utils.travel_state import travel_state
from utils.current_driver import current_driver

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class I2CService:
    MAX_RETRIES = 6
    RETRY_DELAY = 0.1

    def __init__(self, device_address=0x69):
        self.device_address = device_address
        self.bus = None
        self.initialize_i2c()

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

    def MPU_Init(self):
        self.bus.write_byte_data(self.device_address, 0x19, 7)
        self.bus.write_byte_data(self.device_address, 0x6B, 1)
        self.bus.write_byte_data(self.device_address, 0x1A, 0)
        self.bus.write_byte_data(self.device_address, 0x1B, 24)
        self.bus.write_byte_data(self.device_address, 0x38, 1)

    def read_raw_data(self, addr):
        retry_count = 0
        while retry_count < self.MAX_RETRIES:
            try:
                high = self.bus.read_byte_data(self.device_address, addr)
                low = self.bus.read_byte_data(self.device_address, addr + 1)
                value = ((high << 8) | low)
                return value - 65536 if value > 32768 else value
            except OSError as e:
                logger.error(f"Error reading raw data (attempt {retry_count + 1}): {e}")
                retry_count += 1
                time.sleep(self.RETRY_DELAY)
        return 0

class GPSService:
    def __init__(self, gps_port="/dev/ttyACM0", gps_baudrate=115200, gps_timeout=1):
        self.ser = serial.Serial(gps_port, baudrate=gps_baudrate, timeout=gps_timeout)
        self.coordinates = {'latitude': 0.0, 'longitude': 0.0}
        self.coordinates_valid = False
        self.coordinates_lock = threading.Lock()

    def read_gps_data(self, running):
        while running:
            try:
                newdata = self.ser.readline().decode('ascii', errors='replace').strip()
                if newdata.startswith("$GPRMC"):
                    newmsg = pynmea2.parse(newdata)
                    if isinstance(newmsg, pynmea2.RMC) and newmsg.status == 'A':
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
            self.coordinates = new_coordinates

    async def get_current_coordinates_async(self):
        async with asyncio.Lock():
            with self.coordinates_lock:
                if self.coordinates_valid:
                    return self.coordinates
                else:
                    # Valor predeterminado si las coordenadas no son válidas
                    return {'latitude': 16.73, 'longitude': -93.08}

class SensorService:
    G_FORCE_THRESHOLD = 3.5
    DEBOUNCE_TIME = 100

    def __init__(self):
        self.vibration_sw420 = InputDevice(17)
        self.shock_ky031 = InputDevice(27)
        self.i2c_service = I2CService()
        self.vibrations = 0
        self.shocks = 0
        self.last_shock_time = self.millis()
        self.data_buffer = []

    def read_sensors_loop(self, running):
        while running:
            sensor_data = self.read_sensors()
            if sensor_data:
                self.check_for_collision(sensor_data)
                self.data_buffer.append(sensor_data)
            time.sleep(1)

    def read_sensors(self):
        try:
            # Intentar leer los datos de los sensores I2C
            acc_x = self.i2c_service.read_raw_data(0x3B)
            acc_y = self.i2c_service.read_raw_data(0x3D)
            acc_z = self.i2c_service.read_raw_data(0x3F)
            gyro_x = self.i2c_service.read_raw_data(0x43)
            gyro_y = self.i2c_service.read_raw_data(0x45)
            gyro_z = self.i2c_service.read_raw_data(0x47)

            # Procesar datos de aceleración y giroscopio
            Ax = round(acc_x / 16384.0, 2)
            Ay = round(acc_y / 16384.0, 2)
            Az = round(acc_z / 16384.0, 2)
            Axms = round(Ax * 9.81, 2)
            Ayms = round(Ay * 9.81, 2)
            Azms = round(Az * 9.81, 2)
            Gx = round(gyro_x / 131.0, 2)
            Gy = round(gyro_y / 131.0, 2)
            Gz = round(gyro_z / 131.0, 2)

        except Exception as e:
            # En caso de error, usar valores predeterminados
            logger.error(f"Error reading I2C sensors: {e}")
            Axms, Ayms, Azms = 0.0, 0.0, 0.0
            Gx, Gy, Gz = 0.0, 0.0, 0.0

        try:
            if self.vibration_sw420.is_active:
                self.vibrations += 1
            if self.shock_ky031.is_active:
                current_time = self.millis()
                if current_time - self.last_shock_time > self.DEBOUNCE_TIME:
                    self.shocks += 1
                    self.last_shock_time = current_time
        except Exception as e:
            logger.error(f"Error reading GPIO sensors: {e}")
            self.vibrations = 0
            self.shocks = 0

        
        try:
            if self.vibration_sw420.is_active:
                self.vibrations += 1
            if self.shock_ky031.is_active:
                current_time = self.millis()
                if current_time - self.last_shock_time > self.DEBOUNCE_TIME:
                    self.shocks += 1
                    self.last_shock_time = current_time
        except Exception as e:
            logger.error(f"Error reading GPIO sensors: {e}")
            self.vibrations = 0
            self.shocks = 0

        try:
            angle = (Ay - 1) * 180 / (-2) + 0
            angle = int(angle)
            g_force = self.calculate_g_force(Ax, Ay, Az)
        except Exception as e:
            logger.error(f"Error calculating sensor values: {e}")
            angle = 0
            g_force = 0.0


        return {
            'acc_x': Axms, 'acc_y': Ayms, 'acc_z': Azms,
            'gyro_x': Gx, 'gyro_y': Gy, 'gyro_z': Gz,
            'angle': angle,
            'vibrations': self.vibrations,
            'shocks': self.shocks,
            'g_force_x': Ax,
            'g_force_y': Ay,
            'g_force': g_force
        }

    def calculate_averages(self):
        if not self.data_buffer:
            return None

        try:
            avg_data = {
                "acceleration": mean([d['acc_x'] for d in self.data_buffer if d['acc_x'] > 0]) if [d['acc_x'] for d in self.data_buffer if d['acc_x'] > 0] else 0,
                "deceleration": abs(mean([d['acc_x'] for d in self.data_buffer if d['acc_x'] < 0])) if [d['acc_x'] for d in self.data_buffer if d['acc_x'] < 0] else 0,
                "vibrations": sum(d['vibrations'] for d in self.data_buffer),
                "inclination_angle": mean([d['angle'] for d in self.data_buffer]) if [d['angle'] for d in self.data_buffer] else 0,
                "angular_velocity": mean([d['gyro_x'] for d in self.data_buffer]) if [d['gyro_x'] for d in self.data_buffer] else 0,
                "g_force_x": mean([d['g_force_x'] for d in self.data_buffer]) if [d['g_force_x'] for d in self.data_buffer] else 0,
                "g_force_y": mean([d['g_force_y'] for d in self.data_buffer]) if [d['g_force_y'] for d in self.data_buffer] else 0,
            }
        except StatisticsError as e:
            logger.error(f"Statistics error when calculating averages: {e}")
            return None

        return avg_data

    def calculate_g_force(self, x, y, z):
        return (x ** 2 + y ** 2 + z ** 2) ** 0.5

    def millis(self):
        return int(round(time.time() * 1000))

    async def check_for_collision(self, data):
        if data['g_force'] > self.G_FORCE_THRESHOLD:
            logger.warning("Collision detected!")
            await self.send_crash_alert(data)

    async def send_crash_alert(self, data):
        driver_id = await get_last_driver_id() if not travel_state.get_travel_status() else current_driver.get_driver_id()
        crash_model = CrashRequestModel(datetime=datetime.now(), impact_force=data['g_force'], driver_id=driver_id)
        try:
            asyncio.create_task(crash_controller.register_crash_gpio(crash_model))
        except Exception as e:
            logger.error(f"Error sending crash alert: {e}")

class GpioService:
    def __init__(self):
        self.sensor_service = SensorService()
        self.gps_service = GPSService()
        self.rabbitmq_service = RabbitMQService()
        self.database = DatabaseConnector()
        self.kit_id = None
        self.running = True

    async def start(self):
        try:
            self.sensor_thread = threading.Thread(target=self.sensor_service.read_sensors_loop, args=(self.running,))
            self.sensor_thread.start()
            self.gps_thread = threading.Thread(target=self.gps_service.read_gps_data, args=(self.running,))
            self.gps_thread.start()
            await self.rabbitmq_service.connect()
            asyncio.create_task(self.process_and_send_data())
            self.kit_id = await get_kit_id()
            logger.info("GPIO service started")
        except Exception as e:
            logger.error(f"Error starting integrated service: {e}")

    async def stop(self):
        try:
            self.running = False
            self.sensor_thread.join()
            self.gps_thread.join()
            self.gps_service.ser.close()
            await self.rabbitmq_service.close_connection()
            logger.info("GPIO service stopped")
        except Exception as e:
            logger.error(f"Error stopping GPIO service: {e}")

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
            coordinates = await self.gps_service.get_current_coordinates_async()
            coordinates_str = "..."  # Valor predeterminado para coordinates_str
            if coordinates != "Coordinates not valid or sensor calibrating":
                lat = coordinates['latitude']
                lon = coordinates['longitude']
                coordinates_str = f"{lat},{lon}"

            driver_id = await get_last_driver_id() if not travel_state.get_travel_status() else current_driver.get_driver_id()

            message = json.dumps({
                "kit_id": self.kit_id,
                "driver_id": driver_id,
                "datetime": datetime.now().isoformat(),
                "coordinates": coordinates_str
            })

            if self.gps_service.coordinates_valid:
                logger.info(f'Sending coordinates: {message}')
                point = f"POINT({lat} {lon})"
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
                    "coordinates": coordinates_str
                }), "geolocation.status")
        except Exception as e:
            logger.error(f"Error processing GPS data: {e}")

    async def process_sensor_data(self):
        avg_data = self.sensor_service.calculate_averages()
        if avg_data:
            await self.send_driving_data(avg_data)
        self.sensor_service.data_buffer = []

    async def send_driving_data(self, data):
        driving_model = DrivingRequestModel(
            datetime=datetime.now(),
            acceleration=data['acceleration'],
            deceleration=data['deceleration'],
            vibrations=data['vibrations'],
            inclination_angle=data['inclination_angle'],
            angular_velocity=data['angular_velocity'],
            g_force_x=data['g_force_x'],
            g_force_y=data['g_force_y']
        )
        try:
            print('Processing driving data', driving_model)
            await driving_controller.register_driving_gpio(driving_model)
        except Exception as e:
            logger.error(f"Error sending driving data: {e}")

gpio_service = GpioService()