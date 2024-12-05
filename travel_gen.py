import random
from datetime import datetime, timedelta

def generate_random_coordinates(start_coord, range_lat, range_lon):
    """
    Genera una coordenada aleatoria dentro de un rango dado.
    """
    latitude = random.uniform(start_coord[0] - range_lat, start_coord[0] + range_lat)
    longitude = random.uniform(start_coord[1] - range_lon, start_coord[1] + range_lon)
    return round(latitude, 6), round(longitude, 6)

def generate_random_time(start_date, end_date):
    """
    Genera una hora de inicio y una hora de fin aleatorias,
    con una diferencia máxima de 2 horas, en un rango de fechas dado.
    """
    # Generar una fecha aleatoria dentro del rango
    start_date = datetime.strptime(start_date, "%Y-%m-%d")
    end_date = datetime.strptime(end_date, "%Y-%m-%d")
    random_date = start_date + timedelta(days=random.randint(0, (end_date - start_date).days))
    
    # Generar hora de inicio aleatoria entre las 8:00 AM y las 4:00 PM
    start_hour = random.randint(8, 16)  # Hora inicial entre 8 AM y 4 PM
    start_minute = random.randint(0, 59)
    start_time = random_date.replace(hour=start_hour, minute=start_minute, second=0)

    # Generar una duración aleatoria de hasta 2 horas
    duration_seconds = random.randint(300, 7200)  # Entre 5 minutos (300 s) y 2 horas (7200 s)
    end_time = start_time + timedelta(seconds=duration_seconds)

    # Ajustar para no exceder las 6 PM (hora límite del día)
    if end_time.hour > 18:
        end_time = start_time.replace(hour=18, minute=0, second=0)

    return start_time, end_time

def generate_insert_statements(num_travels, start_coord, range_lat, range_lon, driver_ids):
    """
    Genera sentencias SQL INSERT para la tabla travels.
    """
    insert_statements = []

    for _ in range(num_travels):
        # Generar hora de inicio y fin
        start_time, end_time = generate_random_time("2024-11-28", "2024-12-05")

        # Generar coordenadas de inicio y fin
        start_lat, start_lon = generate_random_coordinates(start_coord, range_lat, range_lon)
        end_lat, end_lon = generate_random_coordinates(start_coord, range_lat, range_lon)

        # Generar distancia
        distance_mts = random.uniform(500, 10000)  # Distancia entre 500 y 10,000 metros

        # Seleccionar un driver_id aleatorio
        driver_id = "ababab"

        # Calcular la duración del viaje (HH:MM:SS)
        duration = end_time - start_time

        # Crear sentencia SQL
        insert_statement = f"""
        INSERT INTO travels (driver_id, date, start_hour, end_hour, start_coordinates, end_coordinates, duration, distance_mts)
        VALUES (
            '{driver_id}', 
            '{start_time.date()}', 
            '{start_time}', 
            '{end_time}', 
            ST_GeomFromText('POINT({start_lon} {start_lat})'), 
            ST_GeomFromText('POINT({end_lon} {end_lat})'), 
            '{str(duration)}', 
            {distance_mts:.2f}
        );
        """
        insert_statements.append(insert_statement.strip())

    return insert_statements


# Configuración
start_coordinates = (16.752829568714006, -93.11412099938246)  # Coordenada inicial
range_lat = 0.01  # Rango máximo de latitud (1 km aproximadamente)
range_lon = 0.04  # Rango máximo de longitud (4 km aproximadamente)
driver_ids = ["driver_1", "driver_2", "driver_3", "driver_4", "driver_5"]  # IDs de conductores
num_travels = 50  # Número de viajes a generar

# Generar sentencias
insert_statements = generate_insert_statements(num_travels, start_coordinates, range_lat, range_lon, driver_ids)

# Imprimir sentencias
for statement in insert_statements:
    print(statement)