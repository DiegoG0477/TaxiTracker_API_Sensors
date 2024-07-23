import json
from fastapi import HTTPException, status
from database.connector import DatabaseConnector
from driving.models import DrivingModel
from services.rabbitmq_service import RabbitMQService

database = DatabaseConnector()
rabbitmq_service = RabbitMQService()

def register_driving(driving_model: DrivingModel) -> str:
    try:
        rabbitmq_service.send_message(json.dumps(driving_model.model_dump_json()), "driving.tracking")

        database.query_post(
            """
            INSERT INTO acceleration (kit_id, driver_id, date, data_acceleration, data_desacceleration, inclination_angle, angular_velocity, g_force_x, g_force_y)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s);
            """,
            (
                driving_model.kit_id,
                driving_model.driver_id,
                driving_model.datetime,
                driving_model.acceleration,
                driving_model.deceleration,
                driving_model.inclination_angle,
                driving_model.angular_velocity,
                driving_model.g_force_x,
                driving_model.g_force_y,
            ),
        )

        database.query_post(
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

        database.query_post(
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