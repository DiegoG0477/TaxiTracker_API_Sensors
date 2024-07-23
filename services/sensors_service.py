from datetime import datetime
import threading
import time
from services.geolocation_service import geolocation_service
from crash.controllers import register_crash
from crash.models import CrashRequestModel
from driving.models import DrivingModel
from driving.controllers import register_driving
from gpiozero import InputDevice
import smbus
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SensorService:
    G_FORCE_THRESHOLD = 3.5
    DEBOUNCE_TIME = 100
    MAX_RETRIES = 6
    RETRY_DELAY = 0.1

    def __init__(self):
        self.running = True
        self.is_traveling = False
        self.lock = threading.Lock()
        self.thread = None
        self.kit_id = None
        self.driver_id = None

        # Configuración de los sensores de vibración y choque
        self.vibration_sw420 = InputDevice(17)
        self.shock_ky031 = InputDevice(27)

        # Configuración del MPU6050
        self.bus = None
        self.Device_Address = 0x69
        self.initialize_i2c()

        # Variables para la vibración y el choque
        self.start_time = self.millis()
        self.vibrations = 0
        self.shocks = 0

        self.last_shock_time = self.millis()

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

    def start(self):
        if self.thread is None:
            try:
                logger.info("Starting sensor service thread...")
                self.thread = threading.Thread(target=self.process_sensor_data)
                self.thread.start()
            except Exception as e:
                logger.error(f"Error starting sensor service: {e}")

    def stop(self):
        self.running = False
        if self.thread is not None:
            logger.info("Stopping sensor service thread...")
            self.thread.join()
            self.thread = None

    def start_travel(self, kit_id, driver_id):
        with self.lock:
            self.kit_id = kit_id
            self.driver_id = driver_id
            self.is_traveling = True
        logger.info(f"Starting travel for kit_id: {kit_id}, driver_id: {driver_id}")

    def end_travel(self):
        with self.lock:
            self.is_traveling = False
            self.kit_id = None
            self.driver_id = None
        logger.info("Travel stopped")

    def process_sensor_data(self):
        while self.running:
            with self.lock:
                if self.is_traveling:
                    start_time = time.time()
                    sensor_data = []
                    while time.time() - start_time < 30 and self.is_traveling:
                        data = self.read_sensors()
                        if data is not None:
                            sensor_data.append(data)
                            logger.info(f"Sensor data: {data}")
                            self.check_for_collision(data)
                        else:
                            logger.warning("Failed to read sensor data")
                        time.sleep(0.5)
                    
                    if sensor_data:
                        try:
                            average_data = self.calculate_averages(sensor_data)
                            coordinates = geolocation_service.get_current_coordinates()
                            if not coordinates or coordinates == 'Coordinates not valid or sensor calibrating':
                                coordinates = "..."

                            driving_data = DrivingModel(
                                kit_id=self.kit_id,
                                driver_id=self.driver_id,
                                travel_id=9999,
                                datetime=datetime.now().isoformat(),
                                acceleration=average_data['avg_acceleration'],
                                deceleration=average_data['avg_deceleration'],
                                vibrations=average_data['vibrations'],
                                travel_coordinates=coordinates,
                                inclination_angle=average_data['avg_inclination_angle'],
                                angular_velocity=average_data['avg_angular_velocity'],
                                g_force_x=average_data['avg_g_force_x'],
                                g_force_y=average_data['avg_g_force_y']
                            )
                            
                            register_driving(driving_data)
                            logger.info(f"Driving data: {driving_data}")
                        except Exception as e:
                            logger.error(f"Error processing driving data: {e}")
                else:
                    time.sleep(1)

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
                print(f"Error reading raw data (attempt {retry_count + 1}): {e}")
                retry_count += 1
                time.sleep(self.RETRY_DELAY)
                if retry_count == self.MAX_RETRIES:
                    print(f"Failed to read raw data from address {addr} after multiple attempts")
                    return 0  # or return a default value
                self.initialize_i2c()  # Try to reinitialize the I2C bus

    def process_sensor_data(self):
        while self.running:
            with self.lock:
                if self.is_traveling:
                    start_time = time.time()
                    sensor_data = []
                    while time.time() - start_time < 30 and self.is_traveling:
                        data = self.read_sensors()
                        if data is not None:
                            sensor_data.append(data)
                            # print("Sensor data:", data)
                            self.check_for_collision(data)
                        else:
                            print("Failed to read sensor data")
                        time.sleep(0.5)
                    
                    if sensor_data:
                        try:
                            average_data = self.calculate_averages(sensor_data)
                            coordinates = geolocation_service.get_current_coordinates()
                            if not coordinates or coordinates == 'Coordinates not valid or sensor calibrating':
                                coordinates = "..."

                            driving_data = DrivingModel(
                                kit_id=self.kit_id,
                                driver_id=self.driver_id,
                                travel_id=9999,
                                datetime=datetime.now().isoformat(),
                                acceleration=average_data['avg_acceleration'],
                                deceleration=average_data['avg_deceleration'],
                                vibrations=average_data['vibrations'],
                                travel_coordinates=coordinates,
                                inclination_angle=average_data['avg_inclination_angle'],
                                angular_velocity=average_data['avg_angular_velocity'],
                                g_force_x=average_data['avg_g_force_x'],
                                g_force_y=average_data['avg_g_force_y']
                            )
                            
                            register_driving(driving_data)
                            print("Driving data:", driving_data)
                        except Exception as e:
                            print(f"Error processing driving data: {e}")
                else:
                    time.sleep(1)

    def calculate_averages(self, sensor_data):
        avg_data = {}
        
        # a) Promedio de velocidad de aceleración en m/s
        accelerations = [d['acc_x'] for d in sensor_data if d['acc_x'] > 0]
        avg_data['avg_acceleration'] = sum(accelerations) / len(accelerations) if accelerations else 0
        
        # b) Promedio de velocidad de desaceleración / frenado en m/s
        decelerations = [abs(d['acc_x']) for d in sensor_data if d['acc_x'] < 0]
        avg_data['avg_deceleration'] = sum(decelerations) / len(decelerations) if decelerations else 0
        
        # c) Cantidad de vibraciones
        avg_data['vibrations'] = sensor_data[-1]['vibrations']
        
        # d) Promedio de velocidad angular
        avg_data['avg_angular_velocity'] = sum(abs(d['gyro_x']) + abs(d['gyro_y']) + abs(d['gyro_z']) for d in sensor_data) / (3 * len(sensor_data))
        
        # e) Promedio de ángulo de inclinación (sobre el eje z)
        avg_data['avg_inclination_angle'] = sum(d['angle'] for d in sensor_data) / len(sensor_data)
        
        # f) Promedio de fuerzas G en eje X e Y
        avg_data['avg_g_force_x'] = sum(d['g_force_x'] for d in sensor_data) / len(sensor_data)
        avg_data['avg_g_force_y'] = sum(d['g_force_y'] for d in sensor_data) / len(sensor_data)
        

        return avg_data

    def calculate_g_force(self, Ax, Ay, Az):
        # Calcula la fuerza G basada en las aceleraciones
        return (Ax**2 + Ay**2 + Az**2)**0.5

    def check_for_collision(self, data):
        collision_detected = False
        relevant_data = {
            "shocks": data['shocks'],
            "g_force_x": data['g_force_x'],
            "g_force_y": data['g_force_y'],
            "g_force": data['g_force']
        }

        coordinates = geolocation_service.get_current_coordinates()
        if not coordinates or coordinates == 'Coordinates not valid or sensor calibrating':
            coordinates = "..."  # Valor predeterminado si las coordenadas no son válidas

        crash_data = CrashRequestModel(
            kit_id=self.kit_id,
            driver_id=self.driver_id,
            datetime=datetime.now(),
            impact_force=data['g_force'],
            crash_coordinates=coordinates
        )

        # if data['g_force'] > self.G_FORCE_THRESHOLD:
        #     collision_detected = True
        #     register_crash(crash_data)
        # elif self.shock_ky031.is_active:
        #     collision_detected = True
        #     print('colission detected by shock sensor')
        #     register_crash(crash_data)
        if data['g_force'] > self.G_FORCE_THRESHOLD:
            collision_detected = True
            register_crash(crash_data)

        if collision_detected:
            print("Collision detected:", relevant_data)

    def MPU_Init(self):
        # Inicialización del MPU6050
        self.bus.write_byte_data(self.Device_Address, self.SMPLRT_DIV, 7)
        self.bus.write_byte_data(self.Device_Address, self.PWR_MGMT_1, 1)
        self.bus.write_byte_data(self.Device_Address, self.CONFIG, 0)
        self.bus.write_byte_data(self.Device_Address, self.GYRO_CONFIG, 24)
        self.bus.write_byte_data(self.Device_Address, self.INT_ENABLE, 1)

    def read_raw_data(self, addr):
        # Leer datos crudos del MPU6050
        high = self.bus.read_byte_data(self.Device_Address, addr)
        low = self.bus.read_byte_data(self.Device_Address, addr + 1)
        value = ((high << 8) | low)
        if value > 32768:
            value = value - 65536
        return value

    def millis(self):
        return int(round(time.time() * 1000))

    # Direcciones y registros del MPU6050
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

# Create an instance of SensorService
sensor_service = SensorService()