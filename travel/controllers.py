import json
from fastapi import HTTPException, status
from database.connector import DatabaseConnector
from travel.models import (
    TravelInitRequestModel, 
    TravelFinishRequestModel,
    TravelEntityModel
)
from services.rabbitmq_service import RabbitMQService
from services.sensors_service import sensor_service

database = DatabaseConnector()
rabbitmq_service = RabbitMQService()

def travel_init(travel_model: TravelInitRequestModel) -> str:
    # Check if the driver exists
    driver = get_driver_by_id(travel_model.driver_id)
    if not driver:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Driver not found"
        )
    
    kit = get_kit_id()

    # Iniciar el servicio de sensado
    sensor_service.start_travel(kit['kit_id'], travel_model.driver_id)

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


def travel_finish(travel_model: TravelFinishRequestModel) -> str:
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

    # Insert the complete travel
    return database.query_post(
        """
        INSERT INTO travels (driver_id, date, start_hour, end_hour, start_coordinates, end_coordinates)
        VALUES (%s, %s, %s, %s, ST_GeomFromText(%s), ST_GeomFromText(%s));
        """,
        (
            travel.driver_id,
            travel.date_day,
            travel.start_datetime,
            travel.end_datetime,
            travel.start_coordinates,
            travel.end_coordinates,
        ),
    )


def get_driver_by_id(id: str) -> dict:
    drivers = database.query_get(
        """
        SELECT
            drivers.id,
            drivers.kit_id,
            drivers.name,
            drivers.last_name
        FROM drivers
        WHERE id = %s
        """,
        (id),
    )
    if len(drivers) == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Driver not found"
        )
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