import asyncio
from fastapi import FastAPI
from contextlib import asynccontextmanager
from travel.routers import router as travel_router
from kit.routers import router as kit_router
from geolocation.routers import router as geolocation_router
from services.gpio_service import gpio_service
from services.model_service import ModelGenerator
from database.connector import DatabaseConnector
import threading

db_connector = DatabaseConnector()
stop_event = threading.Event()  # Evento para sincronización de hilos

model_generator = ModelGenerator(db_connector, stop_event)

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Starting GPIO service and Heatmap service")
    
    # Inicia ambos servicios concurrentemente
    gpio_task = asyncio.create_task(gpio_service.start(stop_event))
    model_task = asyncio.create_task(model_generator.run_async())

    yield

    # Detiene ambos servicios
    stop_event.set()
    await gpio_service.stop()
    await model_generator.stop_async()
    await gpio_task
    await model_task

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
    "*"
]

# User APIs
app.include_router(travel_router)
app.include_router(kit_router)
app.include_router(geolocation_router)