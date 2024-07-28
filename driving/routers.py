from fastapi import APIRouter, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from driving.controllers import driving_controller
from driving.models import DrivingModel, DrivingRequestModel
from services.gpio_service import gpio_service
from utils.current_driver import current_driver
from utils.travel_state import travel_state
from travel.controllers import get_kit_id
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter()

@router.post("/driving", response_model=DrivingModel)
async def driving_register_api(request: DrivingRequestModel):
    """
    This driving register API allow you to register a driving.
    """

    if not travel_state.get_travel_status():
        return JSONResponse(status_code=status.HTTP_200_OK, content={"alert": "You must start a travel first"})

    try:
        coordinates = await gpio_service.gps_service.get_current_coordinates_async()
        kit_id = await get_kit_id()
        driver_id = current_driver.get_driver_id()
        driving_details = DrivingModel(
            kit_id=kit_id,
            driver_id=driver_id,
            travel_id=9999,
            datetime=request.datetime,
            acceleration=request.acceleration,
            deceleration=request.deceleration,
            vibrations=request.vibrations,
            travel_coordinates=coordinates,
            inclination_angle=request.inclination_angle,
            angular_velocity=request.angular_velocity,
            g_force_x=request.g_force_x,
            g_force_y=request.g_force_y
        )
        
        driving = await driving_controller.register_driving(driving_details)
        return JSONResponse(status_code=status.HTTP_200_OK, content=jsonable_encoder(driving))
    except Exception as e:
        logger.error(f"Error in driving_register_api: {str(e)}")
        return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content={"error": str(e)})