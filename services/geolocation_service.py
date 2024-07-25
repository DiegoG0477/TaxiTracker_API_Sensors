import threading
import time
import json
import serial
import pynmea2
import asyncio
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
        self.coordinates_lock = asyncio.Lock()

    async def start(self):
        try:
            self.thread = threading.Thread(target=self.read_gps_data)
            self.thread.start()
            await self.rabbitmq_service.connect()  # Connect to RabbitMQ
            asyncio.create_task(self.send_coordinates_periodically())
            self.kit_id = await get_kit_id()
            self.driver_id = await get_last_driver_id()
        except Exception as e:
            print(f"Error starting geolocation service: {e}")

    async def stop(self):
        self.running = False
        self.thread.join()
        self.ser.close()
        await self.rabbitmq_service.close_connection()

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
                print(f"Error reading GPS data: {e}")
                self.coordinates_valid = False

    def update_coordinates(self, new_coordinates):
        with self.coordinates_lock:
            self.current_coordinates = new_coordinates

    async def send_coordinates_periodically(self):
        while self.running:
            try:
                coordinates = await self.get_current_coordinates_async()
                message = json.dumps({
                    "kit_id": self.kit_id,
                    "driver_id": self.driver_id,
                    "datetime": datetime.now().isoformat(),
                    "coordinates": coordinates
                })

                if self.coordinates_valid:
                    print('Sending coordinates:', message)
                    point = f"POINT({coordinates['latitude']} {coordinates['longitude']})"
                    await self.database.query_post(
                        "INSERT INTO geolocation (coordinates, geo_time) VALUES (ST_GeomFromText(%s), %s)",
                        (point, datetime.now())
                    )
                    await self.rabbitmq_service.send_message(message, "geolocation.update")
                else:
                    # print("GPS coordinates are not valid or sensor is calibrating.")
                    await self.rabbitmq_service.send_message(json.dumps({
                        "kit_id": self.kit_id,
                        "driver_id": self.driver_id,
                        "datetime": datetime.now().isoformat(),
                        "coordinates": "..."
                    }), "geolocation.status")
            except Exception as e:
                print(f"Error saving coordinates to DB or sending to RabbitMQ: {e}")
            await asyncio.sleep(3)

    async def get_current_coordinates_async(self):
        async with self.coordinates_lock:
            if self.coordinates_valid:
                return self.current_coordinates
            else:
                return "Coordinates not valid or sensor calibrating"

    async def get_current_coordinates(self):
        return asyncio.run(self.get_current_coordinates_async())

# Inicializar el servicio de geolocalización
geolocation_service = GeolocationService()