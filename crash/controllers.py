import json
from fastapi import HTTPException, status
from database.connector import DatabaseConnector
from crash.models import CrashRequestModel
from services.rabbitmq_service import RabbitMQService

database = DatabaseConnector()
rabbitmq_service = RabbitMQService()

DRIVER_NOT_FOUND = "Driver not found"

def register_crash(crash_model: CrashRequestModel) -> str:
    # Check if the driver exists
    driver = get_driver_by_id(crash_model.driver_id)
    if not driver:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=DRIVER_NOT_FOUND
        )
    
    rabbitmq_service.send_message(json.dumps(crash_model.model_dump_json()), "crash.detected")

    # Insert the crash
    return database.query_post(
        """
        INSERT INTO crashes (kit_id, driver_id, crash_date, impact_g_force, crash_coordinates)
        VALUES (%s, %s, %s, %s, ST_GeomFromText(%s));
        """,
        (
            crash_model.kit_id,
            crash_model.driver_id,
            crash_model.datetime,
            crash_model.impact_force,
            crash_model.crash_coordinates,
        ),
    )


def get_driver_by_id(id: str) -> dict:
    drivers = database.query_get(
        """
        SELECT
        drivers.id,
        drivers.kit_id
        FROM drivers
        WHERE id = %s
        """,
        (id,),
    )
    if len(drivers) == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Driver not found"
        )
    
    driver = drivers[0]
    
    if isinstance(driver, dict):
        return driver
    elif isinstance(driver, (tuple, list)):
        return {
            "id": driver[0],
            "kit_id": driver[1],
        }
    else:
        raise ValueError("Unexpected result format from query_get")