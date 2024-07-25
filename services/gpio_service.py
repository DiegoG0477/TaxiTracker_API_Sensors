import asyncio
import logging
import time
from datetime import datetime
import json
import threading
import serial
import pynmea2
from statistics import mean, StatisticsError
from gpiozero import InputDevice
import smbus
from database.connector import DatabaseConnector
from services.rabbitmq_service import RabbitMQService
from geolocation.controllers import get_kit_id
from driving.controllers import register_driving_gpio

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class GpioService:
    G_FORCE_THRESHOLD = 3.5
    DEBOUNCE_TIME = 100
    MAX_RETRIES = 6
    RETRY_DELAY = 0.1
    DRIVING_URL = "http://localhost:8000/driving"
    CRASH_URL = "http://localhost:8000/crashes"

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
        self.driver_id = None
        self.kit_id = None
        self.running = True
        self.current_coordinates = {'latitude': 0.0, 'longitude': 0.0}
        self.coordinates_valid = False
        self.ser = serial.Serial(gps_port, baudrate=gps_baudrate, timeout=gps_timeout)
        self.coordinates_lock = asyncio.Lock()

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
                # logger.info(f"Sensor data: {sensor_data}")
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
            coordinates = await self.get_current_coordinates_async()
            message = json.dumps({
                "kit_id": self.kit_id,
                "driver_id": self.driver_id,
                "datetime": datetime.now().isoformat(),
                "coordinates": coordinates
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
                    "driver_id": self.driver_id,
                    "datetime": datetime.now().isoformat(),
                    "coordinates": "..."
                }), "geolocation.status")
        except Exception as e:
            logger.error(f"Error processing GPS data: {e}")

    async def process_sensor_data(self):
        avg_data = self.calculate_averages()
        if avg_data:
            self.send_driving_data(avg_data)
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

        print(self.data_buffer)
        
        # Filtrar datos para cada métrica
        acc_x_positive = [d['acc_x'] for d in self.data_buffer if d['acc_x'] > 0]
        acc_x_negative = [d['acc_x'] for d in self.data_buffer if d['acc_x'] < 0]
        angles = [d['angle'] for d in self.data_buffer]
        gyro_x = [d['gyro_x'] for d in self.data_buffer]
        g_force_x = [d['g_force_x'] for d in self.data_buffer]
        g_force_y = [d['g_force_y'] for d in self.data_buffer]
        
        try:
            avg_data = {
                "acceleration": mean(acc_x_positive) if acc_x_positive else 0,
                "deceleration": abs(mean(acc_x_negative)) if acc_x_negative else 0,
                "vibrations": sum(d['vibrations'] for d in self.data_buffer),
                "inclination_angle": mean(angles) if angles else 0,
                "angular_velocity": mean(gyro_x) if gyro_x else 0,
                "g_force_x": mean(g_force_x) if g_force_x else 0,
                "g_force_y": mean(g_force_y) if g_force_y else 0
            }
        except StatisticsError:
            # Manejar el caso en que mean falla debido a listas vacías
            avg_data = {
                "acceleration": 0,
                "deceleration": 0,
                "vibrations": 0,
                "inclination_angle": 0,
                "angular_velocity": 0,
                "g_force_x": 0,
                "g_force_y": 0
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
            register_driving_gpio(payload)  
        except Exception as e:
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

    async def get_current_coordinates_async(self):
        async with self.coordinates_lock:
            if self.coordinates_valid:
                return self.current_coordinates
            else:
                return "Coordinates not valid or sensor calibrating"

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