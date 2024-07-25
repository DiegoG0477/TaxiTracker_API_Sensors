import json
from fastapi import HTTPException, status
from database.connector import DatabaseConnector
from kit.models import KitEntityModel

database = DatabaseConnector()

async def get_kit() -> KitEntityModel:
    kit = await database.query_get(
        """
        SELECT
        kit_id
        FROM kit
        """
    )
    if len(kit) == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No kit found"
        )
    kit = kit[0]
    if isinstance(kit, dict):
        return KitEntityModel(**kit)
    elif isinstance(kit, (tuple, list)):
        return KitEntityModel(kit_id=kit[0])
    else:
        raise ValueError("Unexpected result format from query_get")