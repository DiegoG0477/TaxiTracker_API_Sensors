import threading
import time
import json
import serial
import pynmea2
from datetime import datetime
from database.connector import DatabaseConnector
from services.rabbitmq_service import RabbitMQService
from geolocation.controllers import get_kit_id, get_last_driver_id

class GeolocationService:
    def __init__(self, port="/dev/ttyAMA0", baudrate=9600, timeout=0.5):
        self.rabbitmq_service = RabbitMQService()
        self.database = DatabaseConnector()
        self.driver_id = None
        self.kit_id = None
        self.running = True
        self.current_coordinates = {'latitude': 0.0, 'longitude': 0.0}
        self.coordinates_valid = False
        self.ser = serial.Serial(port, baudrate=baudrate, timeout=timeout)

    def start(self):
        try:
            self.thread = threading.Thread(target=self.read_gps_data)
            self.thread.start()
            self.thread_save_send = threading.Thread(target=self.send_coordinates_periodically)
            self.thread_save_send.start()
            self.kit_id = get_kit_id()
            self.driver_id = get_last_driver_id()
        except Exception as e:
            print(f"Error starting geolocation service: {e}")

    def stop(self):
        self.running = False
        self.thread.join()
        self.thread_save_send.join()
        self.ser.close()
        self.rabbitmq_service.close_connection()

    def read_gps_data(self):
        while self.running:
            try:
                newdata = self.ser.readline().decode('ascii', errors='replace').strip()
                if newdata.startswith("$GPRMC"):
                    newmsg = pynmea2.parse(newdata)
                    if isinstance(newmsg, pynmea2.RMC):
                        if newmsg.status == 'A':
                            self.current_coordinates = {'latitude': newmsg.latitude, 'longitude': newmsg.longitude}
                            self.coordinates_valid = True
                        else:
                            self.coordinates_valid = False
                time.sleep(1)
            except (serial.SerialException, pynmea2.ParseError, UnicodeDecodeError) as e:
                print(f"Error reading GPS data: {e}")
                self.coordinates_valid = False

    def send_coordinates_periodically(self):
        db_conn = self.database.get_connection()
        cursor = db_conn.cursor()
        while self.running:
            try:
                coordinates = self.get_current_coordinates()
                message = json.dumps({
                    "kit_id": self.kit_id,
                    "driver_id": self.driver_id,
                    "datetime": datetime.now().isoformat(),
                    "coordinates": coordinates
                })

                if self.coordinates_valid:
                    point = f"POINT({self.current_coordinates['latitude']} {self.current_coordinates['longitude']})"
                    cursor.execute(
                        "INSERT INTO geolocation (coordinates, geo_time) VALUES (ST_GeomFromText(%s), %s)",
                        (point, datetime.now())
                    )
                    db_conn.commit()
                    self.rabbitmq_service.send_message(message, "geolocation.update")
                else:
                    # print("GPS coordinates are not valid or sensor is calibrating.")
                    self.rabbitmq_service.send_message(json.dumps({
                        "kit_id": self.kit_id,
                        "driver_id": self.driver_id,
                        "datetime": datetime.now().isoformat(),
                        "status": "GPS coordinates are not valid or sensor is calibrating."
                    }), "geolocation.status")

            except Exception as e:
                print(f"Error saving coordinates to DB or sending to RabbitMQ: {e}")
            time.sleep(3)

    def get_current_coordinates(self):
        if self.coordinates_valid:
            coordinates = self.current_coordinates
            return f"POINT({coordinates['latitude']} {coordinates['longitude']})"
        else:
            return "Coordinates not valid or sensor calibrating"

# Inicializar el servicio de geolocalización
geolocation_service = GeolocationService()