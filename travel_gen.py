import random
from datetime import datetime, timedelta

def generate_random_coordinates(start_coord, range_lat, range_lon):
    """
    Genera una coordenada aleatoria dentro de un rango dado.
    """
    latitude = random.uniform(start_coord[0] - range_lat, start_coord[0] + range_lat)
    longitude = random.uniform(start_coord[1] - range_lon, start_coord[1] + range_lon)
    return round(latitude, 6), round(longitude, 6)

def generate_random_time(start_hour, end_hour):
    """
    Genera una hora aleatoria entre dos horarios dados.
    """
    start = datetime.strptime(start_hour, "%H:%M")
    end = datetime.strptime(end_hour, "%H:%M")
    random_time = start + timedelta(seconds=random.randint(0, int((end - start).total_seconds())))
    return random_time

def generate_insert_statements(num_travels, start_coord, range_lat, range_lon, driver_ids):
    """
    Genera sentencias SQL INSERT para la tabla travels.
    """
    insert_statements = []

    for _ in range(num_travels):
        # Generar hora de inicio y duración
        start_time = generate_random_time("08:00", "16:00")
        duration_minutes = random.randint(5, 120)  # Duración entre 5 y 120 minutos
        end_time = start_time + timedelta(minutes=duration_minutes)

        # Generar coordenadas de inicio y fin
        start_lat, start_lon = generate_random_coordinates(start_coord, range_lat, range_lon)
        end_lat, end_lon = generate_random_coordinates(start_coord, range_lat, range_lon)

        # Generar distancia
        distance_mts = random.uniform(500, 10000)  # Distancia entre 500 y 10,000 metros

        # Seleccionar un driver_id aleatorio
        driver_id = random.choice(driver_ids)

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
            '{str(timedelta(minutes=duration_minutes))}', 
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

