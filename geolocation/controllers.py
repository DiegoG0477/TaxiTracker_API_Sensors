from fastapi import HTTPException, status
from database.connector import DatabaseConnector

database = DatabaseConnector()

def get_last_driver_id() -> str:
    driver = database.query_get(
        """
        SELECT
        driver_id
        FROM init_travels
        ORDER BY start_hour DESC
        LIMIT 1
        """
    )
    if len(driver) == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No driver found"
        )
    
    driver = driver[0]
    
    if isinstance(driver, dict):
        return driver["driver_id"]
    elif isinstance(driver, (tuple, list)):
        return driver[0]
    else:
        raise ValueError("Unexpected result format from query_get")

def get_kit_id() -> str:
    kit = database.query_get(
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
        return kit["kit_id"]
    elif isinstance(kit, (tuple, list)):
        return kit[0]
    else:
        raise ValueError("Unexpected result format from query_get")