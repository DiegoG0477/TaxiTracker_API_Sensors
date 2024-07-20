from pydantic import BaseModel
from datetime import datetime
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