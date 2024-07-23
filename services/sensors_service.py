import threading
import time
from datetime import datetime
from gpiozero import InputDevice
import smbus
from services.geolocation_service import geolocation_service
from crash.controllers import register_crash
from crash.models import CrashRequestModel
from driving.models import DrivingModel
from driving.controllers import register_driving

class SensorService:
    G_FORCE_THRESHOLD = 5
    MAX_RETRIES = 8
    RETRY_DELAY = 0.1

    def __init__(self):
        self.running = False
        self.is_traveling = False
        self.lock = threading.Lock()
        self.thread = None
        self.kit_id = None
        self.driver_id = None

        self.vibration_sw420 = InputDevice(17)
        self.shock_ky031 = InputDevice(27)

        self.bus = smbus.SMBus(1)
        self.Device_Address = 0x69
        self.MPU_Init()

        self.start_time = self.millis()
        self.vibrations = 0
        self.shocks = 0

    def start(self):
        if not self.running:
            self.running = True
            self.thread = threading.Thread(target=self.process_sensor_data)
            self.thread.start()

    def stop(self):
        with self.lock:
            self.running = False
        if self.thread:
            self.thread.join()
            self.thread = None

    def start_travel(self, kit_id: str, driver_id: str):
        with self.lock:
            self.kit_id = kit_id
            self.driver_id = driver_id
            self.is_traveling = True
        if not self.running:
            self.start()

    def end_travel(self):
        with self.lock:
            self.is_traveling = False

    def process_sensor_data(self):
        while self.running:
            try:
                with self.lock:
                    if self.is_traveling:
                        start_time = time.time()
                        sensor_data = []
                        while time.time() - start_time < 30 and self.is_traveling:
                            data = self.read_sensors()
                            if data:
                                sensor_data.append(data)
                                self.check_for_collision(data)
                            time.sleep(0.5)
                        if sensor_data:
                            average_data = self.calculate_averages(sensor_data)
                            driving_data = DrivingModel(
                                kit_id=self.kit_id,
                                driver_id=self.driver_id,
                                travel_id=9999,
                                datetime=datetime.now().isoformat(),
                                acceleration=average_data['avg_acceleration'],
                                deceleration=average_data['avg_deceleration'],
                                vibrations=average_data['vibrations'],
                                travel_coordinates=geolocation_service.get_current_coordinates(),
                                inclination_angle=average_data['avg_inclination_angle'],
                                angular_velocity=average_data['avg_angular_velocity'],
                                g_force_x=average_data['avg_g_force_x'],
                                g_force_y=average_data['avg_g_force_y']
                            )
                            register_driving(driving_data)
                            print("Driving data:", driving_data)
                    else:
                        time.sleep(1)
            except Exception as e:
                print(f"Error in process_sensor_data: {e}")
                time.sleep(1)

    def read_sensors(self):
        try:
            acc_x = self.read_raw_data(self.ACCEL_XOUT)
            acc_y = self.read_raw_data(self.ACCEL_YOUT)
            acc_z = self.read_raw_data(self.ACCEL_ZOUT)
            gyro_x = self.read_raw_data(self.GYRO_XOUT)
            gyro_y = self.read_raw_data(self.GYRO_YOUT)
            gyro_z = self.read_raw_data(self.GYRO_ZOUT)

            if None in (acc_x, acc_y, acc_z, gyro_x, gyro_y, gyro_z):
                print("Failed to read sensor data. Skipping this iteration.")
                return None

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
                self.shocks += 1

            angle = int((Ay - 1) * 180 / (-2) + 0)

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
        except Exception as e:
            print(f"Unexpected error in read_sensors: {e}")
            return None

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
        
        # {
        #     'avg_acceleration': 1.2,  # m/s^2
        #     'avg_deceleration': 0.8,  # m/s^2
        #     'vibrations': 45,  # cantidad total de vibraciones detectadas
        #     'avg_angular_velocity': 2.5,  # grados/s
        #     'avg_inclination_angle': 3.2,  # grados
        #     'avg_g_force_x': 0.12,  # G
        #     'avg_g_force_y': 0.08  # G
        # }
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

        crash_data = CrashRequestModel(
            kit_id=self.kit_id,
            driver_id=self.driver_id,
            datetime=datetime.now(),
            impact_force=data['g_force'],
            crash_coordinates=coordinates
        )

        if self.shock_ky031.is_active and data['g_force'] > self.G_FORCE_THRESHOLD:
            collision_detected = True
            print('collision detected by shock sensor and g-force')
            register_crash(crash_data)
        elif self.shock_ky031.is_active:
            print('crash detected by shock sensor')
            register_crash(crash_data)
        elif data['g_force'] > self.G_FORCE_THRESHOLD:
            print('crash detected by g-force')
            register_crash(crash_data)

        if collision_detected:
            print("Collision detected:", relevant_data)

    def MPU_Init(self):
        try:
            self.bus.write_byte_data(self.Device_Address, self.SMPLRT_DIV, 7)
            self.bus.write_byte_data(self.Device_Address, self.PWR_MGMT_1, 1)
            self.bus.write_byte_data(self.Device_Address, self.CONFIG, 0)
            self.bus.write_byte_data(self.Device_Address, self.GYRO_CONFIG, 24)
            self.bus.write_byte_data(self.Device_Address, self.INT_ENABLE, 1)
        except OSError as e:
            print(f"Error initializing MPU6050: {e}")
            return False
        return True

    def read_raw_data(self, addr):
        for _ in range(self.MAX_RETRIES):
            try:
                high = self.bus.read_byte_data(self.Device_Address, addr)
                low = self.bus.read_byte_data(self.Device_Address, addr + 1)
                value = ((high << 8) | low)
                if value > 32768:
                    value = value - 65536
                return value
            except OSError as e:
                print(f"Error reading data: {e}. Retrying...")
                time.sleep(self.RETRY_DELAY)
        print("Failed to read data after multiple attempts")
        return None

    def millis(self):
        return int(round(time.time() * 1000))

    # MPU6050 Registers
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