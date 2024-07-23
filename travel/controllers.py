import json
from typing import Any, Optional
from fastapi import HTTPException, status
from fastapi.responses import JSONResponse
from database.connector import DatabaseConnector
from travel.models import (
    TravelInitControllerModel, 
    TravelFinishRequestModel,
    TravelEntityModel
)
from services.rabbitmq_service import RabbitMQService
from services.sensors_service import sensor_service
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

database = DatabaseConnector()
rabbitmq_service = RabbitMQService()

def travel_init(travel_model: TravelInitControllerModel) -> str:
    try:
        kit_id = get_kit_id()
        driver_id = travel_model.driver_id

        if not kit_id or not driver_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No kit or driver found"
            )

        try:
            database.query_post(
                """
                INSERT INTO init_travels (driver_id, date, start_hour, start_coordinates)
                VALUES (%s, %s, %s, ST_GeomFromText(%s));
                """,
                (
                    travel_model.driver_id,
                    travel_model.date_day,
                    travel_model.start_datetime,
                    travel_model.start_coordinates,
                ),
            )

            sensor_service.start_travel(kit_id, driver_id)

            return travel_model
        except Exception as e:
            logger.error(f"Error starting travel: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    except Exception as e:
        logger.error(f"Error in travel_init: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


def travel_finish(travel_model: TravelFinishRequestModel) -> Any:
    init_data = get_last_init_travel()

    if not init_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No travel found"
        )
    
    # Maneja coordenadas que puedan ser None
    start_coordinates = init_data.get("start_coordinates") or "..."
    end_coordinates = travel_model.end_coordinates or "..."

    try:
        travel = TravelEntityModel(
            driver_id=init_data["driver_id"],
            date_day=init_data["date"],
            start_datetime=init_data["start_hour"],
            end_datetime=travel_model.end_datetime,
            start_coordinates=start_coordinates,
            end_coordinates=end_coordinates,
        )
    except ValueError as e:
        logger.error(f"Validation error: {e}")
        raise HTTPException(status_code=400, detail="Invalid data")

    sensor_service.end_travel()
    
    message = json.dumps(travel.model_dump_json())
    rabbitmq_service.send_message(message, "travel.register")
    
    new_travel_id = database.query_post_travel((
        travel.driver_id,
        travel.date_day,
        travel.start_datetime,
        travel.end_datetime,
        travel.start_coordinates,
        travel.end_coordinates,
    ))
    
    return new_travel_id

def get_driver_by_id(id: str) -> Optional[dict]:
    drivers = database.query_get(
        """
        SELECT
            id,
            kit_id
        FROM drivers
        WHERE id = %s
        """,
        (id,),
    )
    if len(drivers) == 0:
        print("No driver found. The system will add the driver automatically.")
        return None
    return drivers[0]

def get_last_init_travel() -> dict:
    travel = database.query_get(
        """
        SELECT
            driver_id,
            date,
            start_hour,
            start_coordinates
        FROM init_travels
        ORDER BY start_hour DESC
        LIMIT 1
        """
    )
    if len(travel) == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No travel found"
        )
    print("Travel found:", travel)
    return travel[0]

def get_kit_id() -> str:
    kit = database.query_get(
        """
        SELECT
        kit_id
        FROM kit
        """
    )
    if len(kit) == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No kit found"
        )
    kit = kit[0]
    if isinstance(kit, dict):
        return kit["kit_id"]
    elif isinstance(kit, (tuple, list)):
        return kit[0]
    else:
        raise ValueError("Unexpected result format from query_get")
    


def insert_driver(id: str) -> dict:

    kit_id = get_kit_id()

    return database.query_post(
        """
        INSERT INTO drivers (id, kit_id)
        VALUES (%s, %s)
        """,
        (id, kit_id),
    )