import asyncio
import json
from fastapi import HTTPException, status
from database.connector import DatabaseConnector
from driving.models import DrivingModel, DrivingRequestModel
from services.rabbitmq_service import RabbitMQService
from utils.travel_state import travel_state
from utils.current_driver import current_driver
from travel.controllers import travel_controller
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DrivingController:
    def __init__(self, database: DatabaseConnector, rabbitmq_service: RabbitMQService):
        self.database = database
        self.rabbitmq_service = rabbitmq_service

    async def register_driving(self, driving_model: DrivingModel) -> str:
        try:
            message = self.create_driving_message(driving_model)
            await self.rabbitmq_service.send_message(message, "driving.tracking")
            await self.save_driving_data(driving_model)
            return "Driving data registered successfully"
        except Exception as e:
            logger.error(f"Error in register_driving: {e}")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

    async def register_driving_gpio(self, driving_model: DrivingRequestModel) -> str:
        from services.gpio_service import gpio_service
        try:
            if not travel_state.get_travel_status():
                return "Alert, you must start a travel first"
            
            coordinates = await self.get_current_coordinates(gpio_service.gps_service)
            kit_id = await travel_controller.get_kit_id()
            driver_id = current_driver.get_driver_id()

            message = self.create_driving_message(driving_model, kit_id, driver_id, coordinates)

            driving_details = DrivingModel(
                kit_id=kit_id,
                driver_id=driver_id,
                travel_id=9999,
                datetime=driving_model.datetime,
                acceleration=driving_model.acceleration,
                deceleration=driving_model.deceleration,
                vibrations=driving_model.vibrations,
                travel_coordinates=coordinates,
                inclination_angle=driving_model.inclination_angle,
                angular_velocity=driving_model.angular_velocity,
                g_force_x=driving_model.g_force_x,
                g_force_y=driving_model.g_force_y,
            )

            await self.rabbitmq_service.send_message(message, "driving.tracking")
            await self.save_driving_data(driving_details)

            return "Driving data registered successfully"
        except Exception as e:
            logger.error(f"Error in register_driving_gpio: {e}")
            return str(e)

    def create_driving_message(self, driving_model: DrivingModel, kit_id=None, driver_id=None, coordinates=None):
        return json.dumps({
            "kit_id": kit_id or driving_model.kit_id,
            "driver_id": driver_id or driving_model.driver_id,
            "travel_id": driving_model.travel_id,
            "datetime": driving_model.datetime.isoformat(),
            "acceleration": driving_model.acceleration,
            "deceleration": driving_model.deceleration,
            "vibrations": driving_model.vibrations,
            "travel_coordinates": coordinates or driving_model.travel_coordinates,
            "inclination_angle": driving_model.inclination_angle,
            "angular_velocity": driving_model.angular_velocity,
            "g_force_x": driving_model.g_force_x,
            "g_force_y": driving_model.g_force_y,
        })

    async def get_current_coordinates(self, gps_service):
        coordinates = await gps_service.get_current_coordinates_async()
        if not coordinates or coordinates == 'Coordinates not valid or sensor calibrating':
            return "..."
        return f"POINT({coordinates['longitude']} {coordinates['latitude']})"

    async def save_driving_data(self, driving_model: DrivingModel):
        await self.database.query_post(
            """
            INSERT INTO acceleration (kit_id, driver_id, date, data_acceleration, data_deceleration, inclination_angle, angular_velocity, g_force_x, g_force_y)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s);
            """,
            (
                driving_model.kit_id,
                driving_model.driver_id,
                driving_model.datetime.isoformat(),
                driving_model.acceleration,
                driving_model.deceleration,
                driving_model.inclination_angle,
                driving_model.angular_velocity,
                driving_model.g_force_x,
                driving_model.g_force_y,
            ),
        )

        await self.database.query_post(
            """
            INSERT INTO vibrations (kit_id, driver_id, date, data_vibration)
            VALUES (%s, %s, %s, %s);
            """,
            (
                driving_model.kit_id,
                driving_model.driver_id,
                driving_model.datetime,
                driving_model.vibrations,
            ),
        )

        await self.database.query_post(
            """
            INSERT INTO travels_location (travel_id, travel_coordinates, travel_datetime)
            VALUES (%s, ST_GeomFromText(%s), %s);
            """,
            (
                driving_model.travel_id,
                driving_model.travel_coordinates,
                driving_model.datetime,
            ),
        )

    async def register_driving_with_retry(self, driving_data, max_retries=3, retry_delay=1):
        for attempt in range(max_retries):
            try:
                await self.register_driving(driving_data)
                logger.info(f"Driving data registered successfully: {driving_data}")
                return
            except Exception as e:
                logger.error(f"Error registering driving data (attempt {attempt + 1}): {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay)
        logger.error(f"Failed to register driving data after {max_retries} attempts")

# Instanciar el controlador
database = DatabaseConnector()
rabbitmq_service = RabbitMQService()
driving_controller = DrivingController(database, rabbitmq_service)