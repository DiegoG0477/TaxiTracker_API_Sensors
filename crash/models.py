from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class CrashModel(BaseModel):
    kit_id: str
    driver_id: str
    datetime: datetime
    impact_force: float
    crash_coordinates: str

class CrashRequestModel(BaseModel):
    datetime: datetime
    impact_force: float

class CrashResponseModel(BaseModel):
    kit_id: str
    driver_id: str
    datetime: datetime
    impact_force: float
    crash_coordinates: str