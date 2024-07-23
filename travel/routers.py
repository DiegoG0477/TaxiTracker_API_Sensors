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

router = APIRouter()

@router.post("/travels/init", response_model=TravelInitResponseModel)
def travel_init_api(request: TravelInitRequestModel):
    """
    This travel init API allow you to start a travel.
    """
    coordinates = geolocation_service.get_current_coordinates()
    travel_details = TravelInitControllerModel(
        driver_id=request.driver_id,
        date_day=datetime.now().date(),
        start_datetime=datetime.now().isoformat(),
        start_coordinates=coordinates
    )
    travel = travel_init(travel_details)
    return JSONResponse(status_code=status.HTTP_200_OK, content=jsonable_encoder(travel))


@router.post("/travels/finish", response_model=TravelEntityModel)
def travel_finish_api():
    """
    This travel finish API allow you to finish a travel.
    """
    coordinates = geolocation_service.get_current_coordinates()

    travel_details = TravelFinishRequestModel(
        end_datetime=datetime.now().isoformat(),
        end_coordinates=coordinates
    )

    travel = travel_finish(travel_details)
    return JSONResponse(status_code=status.HTTP_200_OK, content=jsonable_encoder(travel))