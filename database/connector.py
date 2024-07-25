import asyncio
import aiomysql
import os
from dotenv import load_dotenv

load_dotenv('local.env') 

class DatabaseConnector:
    def __init__(self):
        self.host = os.getenv("DATABASE_HOST")
        self.user = os.getenv("DATABASE_USERNAME")
        self.password = os.getenv("DATABASE_PASSWORD")
        self.database = os.getenv("DATABASE")
        self.port = int(os.getenv("DATABASE_PORT"))
        if not self.host:
            raise EnvironmentError("DATABASE_HOST environment variable not found")
        if not self.user:
            raise EnvironmentError("DATABASE_USERNAME environment variable not found")
        if not self.password:
            raise EnvironmentError("DATABASE_PASSWORD environment variable not found")
        if not self.database:
            raise EnvironmentError("DATABASE environment variable not found")

    async def get_connection(self):
        return await aiomysql.connect(
            host=self.host,
            port=self.port,
            user=self.user,
            password=self.password,
            db=self.database,
            loop=asyncio.get_event_loop(),
            autocommit=True
        )

    async def query_get(self, sql, param=None):
        try:
            async with self.get_connection() as connection:
                async with connection.cursor(aiomysql.DictCursor) as cursor:
                    await cursor.execute(sql, param)
                    return await cursor.fetchall()
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database error: " + str(e),
            )
        
    async def query_post(self, sql, param):
        try:
            async with self.get_connection() as connection:
                async with connection.cursor() as cursor:
                    await cursor.execute(sql, param)
                    return cursor.lastrowid
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database error: " + str(e),
            )
        
    async def query_post_travel(self, travel_data: Tuple[Any, ...]) -> int:
        try:
            async with self.get_connection() as connection:
                async with connection.cursor() as cursor:
                    # Insertar el viaje
                    await cursor.execute("""
                        INSERT INTO travels (driver_id, date, start_hour, end_hour, start_coordinates, end_coordinates)
                        VALUES (%s, %s, %s, %s, ST_GeomFromText(%s), ST_GeomFromText(%s))
                        RETURNING id;
                    """, travel_data)
                    
                    new_travel_id = await cursor.fetchone()
                    
                    # Actualizar travels_location
                    await cursor.execute("""
                        UPDATE travels_location
                        SET travel_id = %s
                        WHERE travel_id = 9999;
                    """, (new_travel_id,))
                    
                    return new_travel_id
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database error: " + str(e),
            )
