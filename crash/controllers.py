import json
from fastapi import HTTPException, status
from database.connector import DatabaseConnector
from crash.models import CrashRequestModel, CrashModel
from services.rabbitmq_service import RabbitMQService
from travel.controllers import travel_controller
import logging
from services.gpio_service import gpio_service  # Importar servicio GPIO

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DRIVER_NOT_FOUND = "Driver not found"

class CrashController:
    def __init__(self, database: DatabaseConnector, rabbitmq_service: RabbitMQService):
        self.database = database
        self.rabbitmq_service = rabbitmq_service

    async def register_crash(self, crash_model: CrashModel) -> str:
        driver = await self.get_driver_by_id(crash_model.driver_id)
        if not driver:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=DRIVER_NOT_FOUND
            )
        
        crash_message = self.create_crash_message(crash_model)
        await self.rabbitmq_service.send_message(crash_message, "crash.detected")

        await self.save_crash_data(crash_model)

        return "Crash data registered successfully"

    async def register_crash_gpio(self, crash_model: CrashRequestModel) -> str:
        try:
            coordinates = await gpio_service.gps_service.get_current_coordinates_async()

            if not coordinates or coordinates == 'Coordinates not valid or sensor calibrating':
                coordinates = "..."
            else:
                coordinates = f"POINT({coordinates['longitude']} {coordinates['latitude']})"

            kit_id = await travel_controller.get_kit_id()

            driver = await self.get_driver_by_id(crash_model.driver_id)
            if not driver:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=DRIVER_NOT_FOUND
                )

            crash_message = self.create_crash_message(crash_model, kit_id, coordinates)

            crash_details = CrashModel(
                kit_id=kit_id,
                driver_id=crash_model.driver_id,
                datetime=crash_model.datetime,
                impact_force=crash_model.impact_force,
                crash_coordinates=coordinates,
            )
            
            await self.rabbitmq_service.send_message(crash_message, "crash.detected")
            await self.save_crash_data(crash_details)

            return "Crash data registered successfully"
        except Exception as e:
            logger.error(f"Error in register_crash_gpio: {e}")
            return str(e)

    def create_crash_message(self, crash_model: CrashModel, kit_id=None, coordinates=None):
        return json.dumps({
            "kit_id": kit_id or crash_model.kit_id,
            "driver_id": crash_model.driver_id,
            "datetime": crash_model.datetime.isoformat(),
            "impact_force": crash_model.impact_force,
            "crash_coordinates": coordinates or crash_model.crash_coordinates,
        })

    async def save_crash_data(self, crash_model: CrashModel):
        await self.database.query_post(
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

    async def get_driver_by_id(self, driver_id: str) -> dict:
        drivers = await self.database.query_get(
            """
            SELECT id, kit_id FROM drivers WHERE id = %s
            """,
            (driver_id,),
        )
        if not drivers:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=DRIVER_NOT_FOUND
            )
        return drivers[0]

# Instanciar el controlador
database = DatabaseConnector()
rabbitmq_service = RabbitMQService()
crash_controller = CrashController(database, rabbitmq_service)