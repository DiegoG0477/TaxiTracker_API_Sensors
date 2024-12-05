from fastapi import HTTPException, status
from database.connector import DatabaseConnector
from services.model_service import model_buffer
from fastapi import APIRouter, Query, HTTPException, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from typing import Dict, Any

database = DatabaseConnector()

async def get_last_driver_id() -> str:
    try:
        driver = await database.query_get(
            """
            SELECT
            driver_id
            FROM init_travels
            ORDER BY start_hour DESC
            LIMIT 1
            """
        )
        if len(driver) == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="No driver found. Probably no travels registered / done yet"
            )
        
        driver = driver[0]
        
        if isinstance(driver, dict):
            return driver["driver_id"]
        elif isinstance(driver, (tuple, list)):
            return driver[0]
        else:
            raise ValueError("Unexpected result format from query_get")
    except Exception as e:
        return "Error occurred: " + str(e)

async def get_kit_id() -> str:
    try:
        kit = await database.query_get(
            """
            SELECT
            kit_id
            FROM kit
            """
        )
        if len(kit) == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="No kit found. Please register a kit"
            )
        kit = kit[0]
        if isinstance(kit, dict):
            return kit["kit_id"]
        elif isinstance(kit, (tuple, list)):
            return kit[0]
        else:
            raise ValueError("Unexpected result format from query_get")
    except Exception as e:
        return "Error occurred: " + str(e)
    
# async def predict_heatmap(hour: int, day_of_week: int, latitude: float, longitude: float):
#     # Asignar cuadrante basado en coordenadas
#     latitude_mid = 16.75  # Ajustar según datos
#     longitude_mid = -93.1167  # Ajustar según datos

#     if latitude >= latitude_mid and longitude >= longitude_mid:
#         quadrant = 'norte_oriente'
#     elif latitude >= latitude_mid and longitude < longitude_mid:
#         quadrant = 'norte_poniente'
#     elif latitude < latitude_mid and longitude >= longitude_mid:
#         quadrant = 'sur_oriente'
#     else:
#         quadrant = 'sur_poniente'

#     # Obtener modelo del buffer
#     model_key = (hour, quadrant)
#     if model_key not in model_buffer:
#         raise HTTPException(status_code=404, detail="Model not found for the given parameters")

#     model = model_buffer[model_key]

#     # Predicción
#     X = [[hour, day_of_week, latitude, longitude]]
#     prediction = model.predict(X)

#     return {
#         "hour": hour,
#         "quadrant": quadrant,
#         "predictions": prediction.tolist(),
#}


async def predict_heatmap(hour: int, day_of_week: int, latitude: float, longitude: float):
    """
    Endpoint para generar mapas de calor basados en los últimos modelos generados.
    """
    try:
        # Asignar cuadrante basado en coordenadas
        latitude_mid = 16.75  # Ajustar según datos
        longitude_mid = -93.1167  # Ajustar según datos

        # if latitude >= latitude_mid and longitude >= longitude_mid:
        #     quadrant = 'norte_oriente'
        # elif latitude >= latitude_mid and longitude < longitude_mid:
        #     quadrant = 'norte_poniente'
        # elif latitude < latitude_mid and longitude >= longitude_mid:
        #     quadrant = 'sur_oriente'
        # else:
        #     quadrant = 'sur_poniente'

        quadrant = "norte_oriente"

        # Obtener modelo del buffer
        model_key = (hour, quadrant)
        if model_key not in model_buffer:
            raise HTTPException(status_code=404, detail="Model not found for the given parameters")

        model = model_buffer[model_key]

        # Predicción
        X = [[hour, day_of_week, latitude, longitude]]
        prediction = model.predict(X)

        # Retornar predicción en formato JSON
        response = {
            "status": "success",
            "data": {
                "hour": hour,
                "quadrant": quadrant,
                "predictions": prediction.tolist(),
            },
        }
        return JSONResponse(status_code=status.HTTP_200_OK, content=jsonable_encoder(response))

    except HTTPException as e:
        # Manejar modelo no encontrado
        return JSONResponse(
            status_code=e.status_code,
            content={"status": "error", "detail": e.detail},
        )
    except Exception as e:
        # Manejar errores genéricos
        print(f"Error in heatmap prediction: {e}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"status": "error", "detail": str(e)},
        )
