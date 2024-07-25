import json
from fastapi import HTTPException, status
from database.connector import DatabaseConnector
from crash.models import CrashRequestModel, CrashModel
from services.rabbitmq_service import RabbitMQService
from travel.controllers import get_kit_id
from utils.current_driver import current_driver

database = DatabaseConnector()
rabbitmq_service = RabbitMQService()

DRIVER_NOT_FOUND = "Driver not found"

async def register_crash(crash_model: CrashModel) -> str:
    # Check if the driver exists
    driver = await get_driver_by_id(crash_model.driver_id)
    if not driver:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=DRIVER_NOT_FOUND
        )
    
    crash_message = json.dumps({
        "kit_id": crash_model.kit_id,
        "driver_id": crash_model.driver_id,
        "datetime": crash_model.datetime.isoformat(),
        "impact_force": crash_model.impact_force,
        "crash_coordinates": crash_model.crash_coordinates,
    })
    
    await rabbitmq_service.send_message(crash_message, "crash.detected")

    # Insert the crash
    return await database.query_post(
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

async def register_crash_gpio(crash_model: CrashRequestModel) -> str:
    from services.gpio_service import gpio_service
    try:
        coordinates = await gpio_service.get_current_coordinates_async()
        kit_id = await get_kit_id()

        # Check if the driver exists
        driver = await get_driver_by_id(crash_model.driver_id)
        if not driver:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=DRIVER_NOT_FOUND
            )
        
        crash_message = json.dumps({
            "kit_id": kit_id,
            "driver_id": crash_model.driver_id,
            "datetime": crash_model.datetime.isoformat(),
            "impact_force": crash_model.impact_force,
            "crash_coordinates": coordinates,
        })

        crash_details = CrashModel(
            kit_id=kit_id,
            driver_id=crash_model.driver_id,
            datetime=crash_model.datetime,
            impact_force=crash_model.impact_force,
            crash_coordinates=coordinates,
        )
        
        await rabbitmq_service.send_message(crash_message, "crash.detected")

        # Insert the crash
        await database.query_post(
            """
            INSERT INTO crashes (kit_id, driver_id, crash_date, impact_g_force, crash_coordinates)
            VALUES (%s, %s, %s, %s, ST_GeomFromText(%s));
            """,
            (
                crash_details.kit_id,
                crash_details.driver_id,
                crash_details.datetime,
                crash_details.impact_force,
                crash_details.crash_coordinates,
            ),
        )

        return "Crash data registered successfully"
    except Exception as e:
        return str(e)



async def get_driver_by_id(id: str) -> dict:
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