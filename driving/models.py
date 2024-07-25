from pydantic import BaseModel
from datetime import datetime

class DrivingModel(BaseModel):
    kit_id: str
    driver_id: str
    travel_id: int
    datetime: datetime
    acceleration: float
    deceleration: float
    vibrations: int
    travel_coordinates: str
    inclination_angle: float
    angular_velocity: float
    g_force_x: float
    g_force_y: float

class DrivingRequestModel(BaseModel):
    datetime: datetime
    acceleration: float
    deceleration: float
    vibrations: int
    travel_coordinates: str
    inclination_angle: float
    angular_velocity: float
    g_force_x: float
    g_force_y: float