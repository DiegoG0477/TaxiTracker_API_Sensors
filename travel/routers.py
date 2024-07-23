from datetime import datetime
from fastapi import APIRouter, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from travel.controllers import travel_init, travel_finish
from travel.models import (
    TravelInitRequestModel,
    TravelFinishRequestModel,
    TravelInitResponseModel,
    TravelInitControllerModel,
    TravelEntityModel
)
from services.geolocation_service import geolocation_service
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter()

@router.post("/travels/init", response_model=TravelInitResponseModel)
async def travel_init_api(request: TravelInitRequestModel):
    """
    This travel init API allow you to start a travel.
    """
    try:
        coordinates = await geolocation_service.get_current_coordinates_async()
        travel_details = TravelInitControllerModel(
            driver_id=request.driver_id,
            date_day=datetime.now().date(),
            start_datetime=datetime.now().isoformat(),
            start_coordinates=coordinates
        )
        travel = await travel_init(travel_details)
        return JSONResponse(status_code=status.HTTP_200_OK, content=jsonable_encoder(travel))
    except Exception as e:
        logger.error(f"Error in travel_init_api: {str(e)}")
        return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content={"error": str(e)})


@router.post("/travels/finish", response_model=TravelEntityModel)
def travel_finish_api():
    """
    This travel finish API allow you to finish a travel.
    """
    coordinates = geolocation_service.get_current_coordinates()
    if not coordinates or coordinates == 'Coordinates not valid or sensor calibrating':
        coordinates = "..."  # Valor predeterminado si las coordenadas no son válidas

    travel_details = TravelFinishRequestModel(
        end_datetime=datetime.now().isoformat(),
        end_coordinates=coordinates
    )

    travel = travel_finish(travel_details)
    return JSONResponse(status_code=status.HTTP_200_OK, content=jsonable_encoder(travel))