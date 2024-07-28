from fastapi import APIRouter, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from services.gpio_service import gpio_service
from geolocation.models import GeolocationEntityModel

router = APIRouter()

@router.get("/geolocation", response_model=GeolocationEntityModel)
async def get_location_api():
    """
    This API allow you to get the geolocation.
    """
    coordinates = await gpio_service.gps_service.get_current_coordinates_async()

    if coordinates != "Coordinates not valid or sensor calibrating":
        lat = coordinates['latitude']
        lon = coordinates['longitude']
        location = GeolocationEntityModel(lat=lat, long=lon)
    else:
        location = GeolocationEntityModel(lat=0, long=0)

    return JSONResponse(status_code=status.HTTP_200_OK, content=jsonable_encoder(location))