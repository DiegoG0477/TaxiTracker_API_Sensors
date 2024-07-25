from fastapi import APIRouter, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from kit.models import KitEntityModel
from kit.controllers import get_kit

router = APIRouter()

@router.get("/kit/", response_model=KitEntityModel)
async def get_kit_api():
    """
    This API allow you to get the kit information.
    """
    kit = await get_kit()
    return JSONResponse(status_code=status.HTTP_200_OK, content=jsonable_encoder(kit))