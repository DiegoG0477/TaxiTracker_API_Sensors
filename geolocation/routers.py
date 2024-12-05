from fastapi import APIRouter, status, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from services.gpio_service import gpio_service
from geolocation.models import GeolocationEntityModel
from geolocation.controllers import predict_heatmap

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

@router.get("/heatmap")
async def get_heatmap(
    hour: int = Query(..., ge=0, le=23),
    day_of_week: int = Query(..., ge=0, le=6),
    latitude: float = Query(...),
    longitude: float = Query(...),
):
    """
    Endpoint para generar mapas de calor basados en los últimos modelos generados.
    """
    return await predict_heatmap(hour, day_of_week, latitude, longitude)