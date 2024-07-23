import json
from typing import Any, Optional
from fastapi import HTTPException, status
from database.connector import DatabaseConnector
from travel.models import (
    TravelInitControllerModel, 
    TravelFinishRequestModel,
    TravelEntityModel
)
from services.rabbitmq_service import RabbitMQService
from services.sensors_service import sensor_service

database = DatabaseConnector()
rabbitmq_service = RabbitMQService()

def travel_init(travel_model: TravelInitControllerModel) -> str:
    # Check if the driver exists on the local db, if not, add it
    driver = get_driver_by_id(travel_model.driver_id)
    if not driver:
        insert_driver(travel_model.driver_id)
    
    kit_id = get_kit_id()

    # Iniciar el servicio de sensado
    sensor_service.start_travel(kit_id, travel_model.driver_id)

    # Insert the travel
    return database.query_post(
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

def travel_finish(travel_model: TravelFinishRequestModel) -> Any:
    # get the last initiated travel
    init_data = get_last_init_travel()
    if not init_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No travel found"
        )
    
    travel = TravelEntityModel(
        driver_id=init_data.driver_id,
        date_day=init_data.date_day,
        start_datetime=init_data.start_datetime,
        end_datetime=travel_model.end_datetime,
        start_coordinates=init_data.start_coordinates,
        end_coordinates=travel_model.end_coordinates,
    )
    
    # Detener el servicio de sensado
    sensor_service.end_travel()
    
    message = json.dumps(travel.model_dump_json())
    # Send the travel to the RabbitMQ
    rabbitmq_service.send_message(message, "travel.register")
    
    # Insert the complete travel and update travels_location
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