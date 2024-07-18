from pydantic import BaseModel
from typing import Optional
from datetime import datetime, date

# como tal, solo faltaria
# a) finalizar correctamente esta API

# b) hacer los cambios pertinentes en la base de datos
# agregando lo de velocidad angular e inclinacion a la tabla
# correspondiente y a los modelos de driving en Tracking API y Data API

# --- 17 de julio ----

# c) establecer los microservicios de python de matematicas y tabla de frecuencias
# d) conectar los microservicios a la API de lucas
# e) conectar la API de lucas con las graficas del frontend

# f) colocar el servicio de envio de correo en caso de choque 
# en la Tracking API

# --- 18 / 19 de julio ---

# g) conectar la app de electron con esta API
# h) desplegar todo en la nube usando docker

# --- 19 / 20 de julio ---

# i) hacer pruebas de integracion
# --- 21 - 22 de julio ---

class TravelInitRequestModel(BaseModel):
    driver_id: str
    date_day: datetime
    start_datetime: str
    start_coordinates: str

class TravelFinishRequestModel(BaseModel):
    end_datetime: str
    end_coordinates: str

class TravelInitResponseModel(BaseModel):
    driver_id: str
    date_day: datetime
    start_datetime: str
    start_coordinates: str

class TravelEntityModel(BaseModel):
    driver_id: str
    date_day: datetime
    start_datetime: str
    start_coordinates: str
    end_datetime: str
    end_coordinates: str