import json
from typing import Any, Optional
from sqlalchemy.exc import SQLAlchemyError
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

database = DatabaseConnector()
rabbitmq_service = RabbitMQService()

async def travel_init(travel_model: TravelInitControllerModel) -> str:
    try:
        kit_id = await get_kit_id()
        driver_id = travel_model.driver_id
        if not kit_id or not driver_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No kit or driver found"
            )
        
        #metodo para agregar al driver si no existe
        await ensure_driver_exists(driver_id)

        try:
            result = database.query_post(
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

            await sensor_service.start_travel(kit_id, driver_id)

            # return travel_model
            return result
        except Exception as e:
            print(f"Error starting travel: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    except Exception as e:
        print(f"Error in travel_init: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


async def travel_finish(travel_model: TravelFinishRequestModel) -> Any:
    init_data = await get_last_init_travel()

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
        print(f"Validation error: {e}")
        raise HTTPException(status_code=400, detail="Invalid data")

    await sensor_service.end_travel()

    message = json.dumps({
        "driver_id": travel.driver_id,
        "date": travel.date_day.isoformat(),
        "start_hour": travel.start_datetime.isoformat(),
        "end_hour": travel.end_datetime.isoformat(),
        "start_coordinates": travel.start_coordinates,
        "end_coordinates": travel.end_coordinates,
    })

    rabbitmq_service.send_message(message, "travel.register")

    print("Travel finished:", message)
    
    try:
        database.query_post_travel((
            travel.driver_id,
            travel.date_day,
            travel.start_datetime,
            travel.end_datetime,
            travel.start_coordinates,
            travel.end_coordinates,
        ))
    except Exception as e:
        print(f"Error inserting travel into database: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    return travel


async def get_driver_by_id(id: str) -> Optional[dict]:
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

async def get_last_init_travel() -> dict:
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

async def get_kit_id() -> str:
    try:
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
    except Exception as e:
        print(f"Error getting kit ID: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

async def ensure_driver_exists(driver_id: str):
    try:
        print("known driver")
        result = await database.query_post(
            """
            SELECT 1 FROM taxitracker.drivers WHERE id = %s
            """,
            (driver_id,)
        )
        if not result:
            print("driver doesn't exists, it will be registered automatically")            
            await database.query_post(
                """
                INSERT INTO taxitracker.drivers (id, column1, column2, ...)
                VALUES (%s, value1, value2, ...)
                """,
                (driver_id,)
            )
    except SQLAlchemyError as e:
        print(f"Error ensuring driver existence: {e}")
        raise HTTPException(status_code=500, detail="Error ensuring driver existence")