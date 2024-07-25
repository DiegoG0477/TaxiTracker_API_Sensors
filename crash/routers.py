from datetime import datetime
from fastapi import APIRouter, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from crash.controllers import register_crash
from crash.models import CrashModel, CrashRequestModel
from services.gpio_service import gpio_service
from utils.current_driver import current_driver
from travel.controllers import get_kit_id
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter()

@router.post("/crashes", response_model=CrashModel)
async def api_register_crash(request: CrashRequestModel):
    """
    This driving register API allow you to register a driving.
    """

    try:
        coordinates = await gpio_service.get_current_coordinates_async()
        kit_id = await get_kit_id()
        driver_id = current_driver.get_driver_id()

        crash_details = CrashModel(
            kit_id=kit_id,
            driver_id=driver_id,
            datetime=request.datetime,
            impact_force=request.impact_force,
            crash_coordinates=coordinates,
        )
        
        crash = await register_crash(crash_details)
        return JSONResponse(status_code=status.HTTP_200_OK, content=jsonable_encoder(crash))
    except Exception as e:
        logger.error(f"Error in driving_register_api: {str(e)}")
        return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content={"error": str(e)})