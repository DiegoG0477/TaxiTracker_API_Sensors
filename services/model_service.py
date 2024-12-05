import threading
import asyncio
import pandas as pd
from sklearn.cluster import DBSCAN
from sklearn.model_selection import train_test_split
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
import logging
from database.connector import DatabaseConnector

# Configuración del logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Buffer para almacenar los modelos generados
model_buffer = {}

# Hilo productor: Genera modelos cada 3 minutos
class ModelGenerator:
    def __init__(self, db_connector: DatabaseConnector, stop_event: threading.Event, interval=180):
        self.interval = interval
        self.running = False
        self.db_connector = db_connector
        self.stop_event = stop_event

    async def run_async(self):
        self.running = True
        while not self.stop_event.is_set():
            try:
                logger.info("Generating models...")
                await self.generate_models()  # Lógica asincrónica
                logger.info("Models generated successfully.")
            except Exception as e:
                logger.error(f"Error generating models: {e}")
            await asyncio.sleep(self.interval)

    async def stop_async(self):
        self.running = False

    async def generate_models(self):
        query = '''
        SELECT driver_id, date, start_hour, start_coordinates, end_coordinates, duration, distance_mts
        FROM travels
        '''
        try:
            # Cargar datos desde la base de datos
            results = await self.db_connector.query_get(query)
            df = pd.DataFrame(results)

            if df.empty:
                logger.warning("No data retrieved from database.")
                return

            # Procesar columnas necesarias
            df['start_latitude'] = df['start_coordinates'].apply(lambda x: x[1])
            df['start_longitude'] = df['start_coordinates'].apply(lambda x: x[0])
            df['hour'] = pd.to_datetime(df['start_hour']).dt.hour
            df['day_of_week'] = pd.to_datetime(df['start_hour']).dt.dayofweek

            latitude_mid = df['start_latitude'].mean()
            longitude_mid = df['start_longitude'].mean()

            def assign_quadrant(row):
                if row['start_latitude'] >= latitude_mid and row['start_longitude'] >= longitude_mid:
                    return 'norte_oriente'
                elif row['start_latitude'] >= latitude_mid and row['start_longitude'] < longitude_mid:
                    return 'norte_poniente'
                elif row['start_latitude'] < latitude_mid and row['start_longitude'] >= longitude_mid:
                    return 'sur_oriente'
                else:
                    return 'sur_poniente'

            df['quadrant'] = df.apply(assign_quadrant, axis=1)

            # Generar modelos por hora y cuadrante
            for hour in range(24):
                hourly_data = df[df['hour'] == hour]
                if len(hourly_data) < 10:  # Filtrar horas con pocos datos
                    logger.warning(f"Skipping hour {hour} due to insufficient data.")
                    continue

                for quadrant in hourly_data['quadrant'].unique():
                    quadrant_data = hourly_data[hourly_data['quadrant'] == quadrant]
                    coords = quadrant_data[['start_latitude', 'start_longitude']].values

                    # Escalar coordenadas
                    scaler = StandardScaler()
                    coords_scaled = scaler.fit_transform(coords)

                    # Clustering con DBSCAN
                    db = DBSCAN(eps=0.1, min_samples=2).fit(coords_scaled)
                    quadrant_data['zone'] = db.labels_

                    # Loguear cantidad de clústeres
                    num_clusters = len(set(db.labels_)) - (1 if -1 in db.labels_ else 0)
                    logger.info(f"DBSCAN detected {num_clusters} clusters for hour {hour}, quadrant {quadrant}.")

                    # Filtrar outliers (-1)
                    quadrant_data = quadrant_data[quadrant_data['zone'] != -1]

                    if quadrant_data.empty or len(quadrant_data['zone'].unique()) < 2:
                        logger.warning(f"Skipping model generation for hour {hour}, quadrant {quadrant}. Not enough data diversity.")
                        continue

                    # Variables predictoras y objetivo
                    X = quadrant_data[['hour', 'day_of_week', 'start_latitude', 'start_longitude']]
                    y = quadrant_data['zone']

                    # Dividir datos para entrenamiento y validación
                    X_train, _, y_train, _ = train_test_split(X, y, test_size=0.2, random_state=42)

                    # Entrenar modelo de regresión logística
                    model = LogisticRegression()
                    model.fit(X_train, y_train)

                    # Guardar el modelo en el buffer
                    model_buffer[(hour, quadrant)] = model

            # Loguear resultados finales
            logger.info(f"Generated {len(model_buffer)} models successfully.")
            logger.debug(f"Model buffer: {model_buffer.keys()}")

        except Exception as e:
            logger.error(f"Error processing models: {e}")
