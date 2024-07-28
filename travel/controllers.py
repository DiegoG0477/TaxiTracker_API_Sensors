import json
from typing import Any, Optional
from fastapi import HTTPException, status
from database.connector import DatabaseConnector
from travel.models import TravelInitControllerModel, TravelFinishRequestModel, TravelEntityModel
from services.rabbitmq_service import RabbitMQService
from utils.travel_state import travel_state
from utils.current_driver import current_driver
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TravelController:
    def __init__(self, database: DatabaseConnector, rabbitmq_service: RabbitMQService):
        self.database = database
        self.rabbitmq_service = rabbitmq_service

    async def travel_init(self, travel_model: TravelInitControllerModel) -> str:
        try:
            kit_id = await self.get_kit_id()
            driver_id = travel_model.driver_id

            if not kit_id or not driver_id:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No kit or driver found")

            await self.ensure_driver_exists(driver_id)

            travel_state.start_travel()
            current_driver.define_driver(driver_id)

            await self.database.query_post(
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

            return "Travel initiated successfully"
        except Exception as e:
            logger.error(f"Error in travel_init: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def travel_finish(self, travel_model: TravelFinishRequestModel) -> Any:
        try:
            init_data = await self.get_last_init_travel()
            if not init_data:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No travel found")

            travel = TravelEntityModel(
                driver_id=init_data["driver_id"],
                date_day=init_data["date"],
                start_datetime=init_data["start_hour"],
                end_datetime=travel_model.end_datetime,
                start_coordinates=init_data.get("start_coordinates") or "...",
                end_coordinates=travel_model.end_coordinates,
            )

            travel_state.end_travel()
            current_driver.end_driver_travel()

            message = self.create_travel_message(travel)
            await self.rabbitmq_service.send_message(message, "travel.register")

            await self.database.query_post(
                """
                INSERT INTO travels (driver_id, date_day, start_datetime, end_datetime, start_coordinates, end_coordinates)
                VALUES (%s, %s, %s, %s, ST_GeomFromText(%s), ST_GeomFromText(%s));
                """,
                (
                    travel.driver_id,
                    travel.date_day,
                    travel.start_datetime,
                    travel.end_datetime,
                    travel.start_coordinates,
                    travel.end_coordinates,
                )
            )

            return travel
        except Exception as e:
            logger.error(f"Error in travel_finish: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    def create_travel_message(self, travel: TravelEntityModel):
        return json.dumps({
            "driver_id": travel.driver_id,
            "date": travel.date_day.isoformat(),
            "start_hour": travel.start_datetime.isoformat(),
            "end_hour": travel.end_datetime.isoformat(),
            "start_coordinates": travel.start_coordinates,
            "end_coordinates": travel.end_coordinates,
        })

    async def get_driver_by_id(self, driver_id: str) -> Optional[dict]:
        drivers = await self.database.query_get(
            """
            SELECT id, kit_id FROM drivers WHERE id = %s
            """, (driver_id,)
        )
        if not drivers:
            logger.info("No driver found. The system will add the driver automatically.")
            return None
        return drivers[0]

    async def get_last_init_travel(self) -> dict:
        travel = await self.database.query_get(
            """
            SELECT driver_id, date, start_hour, start_coordinates
            FROM init_travels
            ORDER BY start_hour DESC
            LIMIT 1
            """
        )
        if not travel:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No travel found")
        return travel[0]

    async def get_kit_id(self) -> str:
        kit = await self.database.query_get(
            """
            SELECT kit_id FROM kit
            """
        )
        if not kit:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No kit found")
        return kit[0]["kit_id"]

    async def ensure_driver_exists(self, driver_id: str):
        result = await self.database.query_get(
            """
            SELECT 1 FROM drivers WHERE id = %s
            """, (driver_id,)
        )
        if not result:
            kit_id = await self.get_kit_id()
            await self.database.query_post(
                """
                INSERT INTO drivers (id, kit_id)
                VALUES (%s, %s)
                """, (driver_id, kit_id)
            )

database = DatabaseConnector()
rabbitmq_service = RabbitMQService()
travel_controller = TravelController(database, rabbitmq_service)