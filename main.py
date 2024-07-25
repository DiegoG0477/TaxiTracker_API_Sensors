from fastapi import FastAPI
from contextlib import asynccontextmanager
from travel.routers import router as travel_router
from kit.routers import router as kit_router
from services.gpio_service import gpio_service

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Código que se ejecuta antes de que la aplicación inicie
    print("Starting GPIO service")
    await gpio_service.start()
    yield
    # Código que se ejecuta cuando la aplicación se está cerrando
    await gpio_service.stop()

# Set API info
app = FastAPI(
    title="TaxiTracker Local Fastapi API",
    description="This is an API designed for TaxiTracker Local Database and some electron requests.",
    lifespan=lifespan
)

# Set CORS
origins = [
    # "http://localhost",
    # "http://localhost:8000",
    # "http://localhost:3000",
    # "http://localhost:3001",
    # "http://localhost:5176",
    # "http://localhost:4000",
    # "http://localhost:19006",
    # Add your frontend URL here...
    "*",
]

"""
User APIs
Provides user CRUD APIs.
"""

app.include_router(travel_router)
app.include_router(kit_router)