from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class TravelInitRequestModel(BaseModel):
    driver_id: str

class TravelInitControllerModel(BaseModel):
    driver_id: str
    date_day: datetime
    start_datetime: datetime
    start_coordinates: Optional[str]  # Cambiado a Optional

class TravelFinishRequestModel(BaseModel):
    end_datetime: datetime
    end_coordinates: Optional[str]  # Cambiado a Optional

class TravelInitResponseModel(BaseModel):
    driver_id: str
    date_day: datetime
    start_datetime: datetime
    start_coordinates: Optional[str]  # Cambiado a Optional

class TravelEntityModel(BaseModel):
    driver_id: str
    date_day: datetime
    start_datetime: datetime
    start_coordinates: Optional[str]  # Cambiado a Optional
    end_datetime: datetime
    end_coordinates: Optional[str]  # Cambiado a Optionals