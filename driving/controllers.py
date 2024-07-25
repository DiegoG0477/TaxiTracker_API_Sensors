import json
from fastapi import HTTPException, status
from database.connector import DatabaseConnector
from driving.models import DrivingModel, DrivingRequestModel
import time
from services.rabbitmq_service import RabbitMQService
from utils.travel_state import travel_state
from utils.current_driver import current_driver
from travel.controllers import get_kit_id
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

database = DatabaseConnector()
rabbitmq_service = RabbitMQService()

async def register_driving(driving_model: DrivingModel) -> str:
    try:                
        print('sending driving data to rabbitmq')
        message = json.dumps({
            "kit_id": driving_model.kit_id,
            "driver_id": driving_model.driver_id,
            "travel_id": driving_model.travel_id,
            "datetime": driving_model.datetime.isoformat(),
            "acceleration": driving_model.acceleration,
            "deceleration": driving_model.deceleration,
            "vibrations": driving_model.vibrations,
            "travel_coordinates": driving_model.travel_coordinates,
            "inclination_angle": driving_model.inclination_angle,
            "angular_velocity": driving_model.angular_velocity,
            "g_force_x": driving_model.g_force_x,
            "g_force_y": driving_model.g_force_y,
        })

        await rabbitmq_service.send_message(message, "driving.tracking")

        await database.query_post(
            """
            INSERT INTO acceleration (kit_id, driver_id, date, data_acceleration, data_desacceleration, inclination_angle, angular_velocity, g_force_x, g_force_y)
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

        await database.query_post(
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

        await database.query_post(
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

        return "Driving data registered successfully"
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

async def register_driving_gpio(driving_model: DrivingRequestModel) -> str:
    from services.gpio_service import gpio_service
    try:
        print('sending driving data to rabbitmq')

        if not travel_state.get_travel_status():
            return ("alert, you must start a travel first")
        coordinates = await gpio_service.get_current_coordinates_async()
        kit_id = await get_kit_id()
        driver_id = current_driver.get_driver_id()

        message = json.dumps({
            "kit_id": kit_id,
            "driver_id": driver_id,
            "travel_id": coordinates,
            "datetime": driving_model.datetime.isoformat(),
            "acceleration": driving_model.acceleration,
            "deceleration": driving_model.deceleration,
            "vibrations": driving_model.vibrations,
            "travel_coordinates": driving_model.travel_coordinates,
            "inclination_angle": driving_model.inclination_angle,
            "angular_velocity": driving_model.angular_velocity,
            "g_force_x": driving_model.g_force_x,
            "g_force_y": driving_model.g_force_y,
        })

        driving_details = DrivingModel(
            kit_id=kit_id,
            driver_id=driver_id,
            travel_id=coordinates,
            datetime=driving_model.datetime,
            acceleration=driving_model.acceleration,
            deceleration=driving_model.deceleration,
            vibrations=driving_model.vibrations,
            travel_coordinates=driving_model.travel_coordinates,
            inclination_angle=driving_model.inclination_angle,
            angular_velocity=driving_model.angular_velocity,
            g_force_x=driving_model.g_force_x,
            g_force_y=driving_model.g_force_y,
        )

        await rabbitmq_service.send_message(message, "driving.tracking")

        await database.query_post(
            """
            INSERT INTO acceleration (kit_id, driver_id, date, data_acceleration, data_desacceleration, inclination_angle, angular_velocity, g_force_x, g_force_y)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s);
            """,
            (
                driving_details.kit_id,
                driving_details.driver_id,
                driving_details.datetime.isoformat(),
                driving_details.acceleration,
                driving_details.deceleration,
                driving_details.inclination_angle,
                driving_details.angular_velocity,
                driving_details.g_force_x,
                driving_details.g_force_y,
            ),
        )

        await database.query_post(
            """
            INSERT INTO vibrations (kit_id, driver_id, date, data_vibration)
            VALUES (%s, %s, %s, %s);
            """,
            (
                driving_details.kit_id,
                driving_details.driver_id,
                driving_details.datetime,
                driving_details.vibrations,
            ),
        )

        await database.query_post(
            """
            INSERT INTO travels_location (travel_id, travel_coordinates, travel_datetime)
            VALUES (%s, ST_GeomFromText(%s), %s);
            """,
            (
                driving_details.travel_id,
                driving_details.travel_coordinates,
                driving_details.datetime,
            ),
        )

        return "Driving data registered successfully"
    except Exception as e:
        print(f"Error in register_driving_gpio: {str(e)}")
        return str(e)

async def register_driving_with_retry(driving_data, max_retries=3, retry_delay=1):
    for attempt in range(max_retries):
        try:
            await register_driving(driving_data)
            logger.info(f"Driving data registered successfully: {driving_data}")
            return
        except Exception as e:
            logger.error(f"Error registering driving data (attempt {attempt + 1}): {e}")
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
    logger.error(f"Failed to register driving data after {max_retries} attempts")