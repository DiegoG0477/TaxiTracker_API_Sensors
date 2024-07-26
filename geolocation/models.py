from pydantic import BaseModel

class GeolocationEntityModel(BaseModel):
    lat: float
    long: float