import asyncio
import logging
import threading
import queue
import time
import json
from datetime import datetime
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


### Sensor Threads ###
class SensorThread(threading.Thread):
    def __init__(self, name, read_function, data_queue):
        super().__init__()
        self.name = name
        self.read_function = read_function
        self.data_queue = data_queue
        self.running = True

    def run(self):
        logger.info(f"Starting {self.name} thread.")
        while self.running:
            try:
                data = self.read_function()
                timestamped_data = {"sensor_name": self.name, "data": data, "timestamp": datetime.now()}
                self.data_queue.put(timestamped_data)
                time.sleep(1)  # Evita sobrecargar el hilo
            except Exception as e:
                logger.error(f"Error in {self.name} thread: {e}")

    def stop(self):
        self.running = False
        logger.info(f"Stopping {self.name} thread.")


### I2C Service ###
class I2CService:
    MAX_RETRIES = 6
    RETRY_DELAY = 0.1

    def __init__(self, device_address=0x69):
        self.device_address = device_address
        self.bus = None
        self.initialize_i2c()

    def initialize_i2c(self):
        for attempt in range(self.MAX_RETRIES):
            try:
                self.bus = smbus.SMBus(1)
                self.MPU_Init()
                logger.info("I2C bus initialized successfully.")
                return
            except OSError as e:
                logger.error(f"Error initializing I2C bus (attempt {attempt + 1}): {e}")
                time.sleep(self.RETRY_DELAY)
        logger.error("Failed to initialize I2C bus after multiple attempts.")

    def MPU_Init(self):
        # Inicializar el MPU-6050
        self.bus.write_byte_data(self.device_address, 0x19, 7)
        self.bus.write_byte_data(self.device_address, 0x6B, 1)
        self.bus.write_byte_data(self.device_address, 0x1A, 0)
        self.bus.write_byte_data(self.device_address, 0x1B, 24)
        self.bus.write_byte_data(self.device_address, 0x38, 1)

    def read_raw_data(self, addr):
        try:
            high = self.bus.read_byte_data(self.device_address, addr)
            low = self.bus.read_byte_data(self.device_address, addr + 1)
            value = ((high << 8) | low)
            return value - 65536 if value > 32768 else value
        except OSError as e:
            logger.error(f"Error reading raw data from I2C: {e}")
            return 0


### GPS Service ###
class GPSService:
    def __init__(self, gps_port="/dev/ttyS0", gps_baudrate=115200, gps_timeout=1):
        self.ser = serial.Serial(gps_port, baudrate=gps_baudrate, timeout=gps_timeout)
        self.coordinates = {"latitude": 0.0, "longitude": 0.0}
        self.coordinates_valid = False
        self.coordinates_lock = threading.Lock()

    def read_gps_data(self):
        try:
            newdata = self.ser.readline().decode("ascii", errors="replace").strip()
            if newdata.startswith("$GPRMC"):
                newmsg = pynmea2.parse(newdata)
                if isinstance(newmsg, pynmea2.RMC) and newmsg.status == "A":
                    self.update_coordinates({"latitude": newmsg.latitude, "longitude": newmsg.longitude})
                    self.coordinates_valid = True
                else:
                    self.coordinates_valid = False
            return {"latitude": self.coordinates["latitude"], "longitude": self.coordinates["longitude"]}
        except (serial.SerialException, pynmea2.ParseError, UnicodeDecodeError) as e:
            logger.error(f"Error reading GPS data: {e}")
            return {"latitude": 0.0, "longitude": 0.0}

    def update_coordinates(self, new_coordinates):
        with self.coordinates_lock:
            self.coordinates = new_coordinates

    async def get_current_coordinates_async(self):
        async with asyncio.Lock():
            with self.coordinates_lock:
                return self.coordinates if self.coordinates_valid else {"latitude": 0.0, "longitude": 0.0}


### Sensor Service ###
class SensorService:
    G_FORCE_THRESHOLD = 3.5

    def __init__(self):
        self.i2c_service = I2CService()
        self.vibration_sw420 = InputDevice(17)
        self.shock_ky031 = InputDevice(27)

    def read_sensors(self):
        try:
            acc_x = self.i2c_service.read_raw_data(0x3B)
            acc_y = self.i2c_service.read_raw_data(0x3D)
            acc_z = self.i2c_service.read_raw_data(0x3F)
            return {
                "acc_x": acc_x / 16384.0,
                "acc_y": acc_y / 16384.0,
                "acc_z": acc_z / 16384.0,
                "vibration": self.vibration_sw420.is_active,
                "shock": self.shock_ky031.is_active,
            }
        except Exception as e:
            logger.error(f"Error reading sensors: {e}")
            return {}


### GPIO Service ###
class GpioService:
    def __init__(self):
        self.data_queue = queue.Queue()
        self.gps_service = GPSService()
        self.sensor_service = SensorService()
        self.rabbitmq_service = RabbitMQService()
        self.database = DatabaseConnector()
        self.threads = []
        self.running = True

    async def start(self):
        try:
            self.threads.append(SensorThread("gps", self.gps_service.read_gps_data, self.data_queue))
            self.threads.append(SensorThread("sensors", self.sensor_service.read_sensors, self.data_queue))
            for thread in self.threads:
                thread.start()
            asyncio.create_task(self.process_data())
            logger.info("GPIO service started.")
        except Exception as e:
            logger.error(f"Error starting GPIO service: {e}")

    async def stop(self):
        self.running = False
        for thread in self.threads:
            thread.stop()
            thread.join()
        logger.info("GPIO service stopped.")

    async def process_data(self):
        while self.running:
            try:
                data = self.data_queue.get(timeout=1)
                if data["sensor_name"] == "gps":
                    await self.process_gps_data(data["data"])
                elif data["sensor_name"] == "sensors":
                    await self.process_sensor_data(data["data"])
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Error processing data: {e}")

    async def process_gps_data(self, gps_data):
        try:
            message = {
                "datetime": datetime.now().isoformat(),
                "coordinates": gps_data,
            }
            logger.info(f"Processed GPS data: {message}")
            await self.rabbitmq_service.send_message(json.dumps(message), "geolocation.update")
        except Exception as e:
            logger.error(f"Error processing GPS data: {e}")

    async def process_sensor_data(self, sensor_data):
        try:
            logger.info(f"Processed sensor data: {sensor_data}")
            # Aquí puedes enviar los datos a RabbitMQ o la base de datos
        except Exception as e:
            logger.error(f"Error processing sensor data: {e}")


gpio_service = GpioService()