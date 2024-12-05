import asyncio
from fastapi import FastAPI
from contextlib import asynccontextmanager
from travel.routers import router as travel_router
from kit.routers import router as kit_router
from geolocation.routers import router as geolocation_router
from services.gpio_service import gpio_service
from services.model_service import ModelGenerator

model_generator = ModelGenerator()

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Starting GPIO service")
    await gpio_service.start()
    print("Starting heatmap service")
    model_generator.start()
    yield
    await gpio_service.stop()
    model_generator.stop()

# Set API info
app = FastAPI(
    title="TaxiTracker Local Fastapi API",
    description="This is an API designed for TaxiTracker Local Database and some electron requests.",
    lifespan=lifespan
)

origins = [
    "http://localhost:3000",
    "http://localhost:3001",
    "http://localhost:5176",
]

"""
User APIs
Provides user CRUD APIs.
"""

app.include_router(travel_router)
app.include_router(kit_router)
app.include_router(geolocation_router)