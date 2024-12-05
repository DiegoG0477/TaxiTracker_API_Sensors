from sklearn.cluster import DBSCAN
from sklearn.linear_model import LogisticRegression
from sklearn.dummy import DummyClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
import numpy as np
import logging
import pandas as pd

# Configuración del logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

model_buffer = {}

class ModelGenerator:
    async def generate_models(self):
        query = '''
        SELECT driver_id, date, start_hour, start_coordinates, end_coordinates, duration, distance_mts
        FROM travels
        '''
        try:
            results = await self.db_connector.query_get(query)
            df = pd.DataFrame(results)

            if df.empty:
                logger.warning("No data retrieved from database.")
                return

            df['start_latitude'] = df['start_coordinates'].apply(lambda x: x[1])
            df['start_longitude'] = df['start_coordinates'].apply(lambda x: x[0])
            df['hour'] = pd.to_datetime(df['start_hour']).dt.hour
            df['day_of_week'] = pd.to_datetime(df['start_hour']).dt.dayofweek

            latitude_mid = 16.752143
            longitude_mid = -93.106897

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

            for hour in range(24):
                hourly_data = df[df['hour'] == hour]
                if len(hourly_data) < 1:
                    continue

                for quadrant in hourly_data['quadrant'].unique():
                    quadrant_data = hourly_data[hourly_data['quadrant'] == quadrant]
                    coords = quadrant_data[['start_latitude', 'start_longitude']].values
                    scaler = StandardScaler()
                    coords_scaled = scaler.fit_transform(coords)
                    db = DBSCAN(eps=0.05, min_samples=1).fit(coords_scaled)  # Más permisivo
                    quadrant_data['zone'] = db.labels_

                    # Reemplazar outliers (-1) por una nueva zona
                    quadrant_data['zone'] = quadrant_data['zone'].replace(-1, 0)

                    if quadrant_data.empty:
                        logger.warning(f"No clusters found for hour {hour}, quadrant {quadrant}.")
                        continue

                    X = quadrant_data[['hour', 'day_of_week', 'start_latitude', 'start_longitude']]
                    y = quadrant_data['zone']

                    if len(set(y)) < 2:
                        logger.info(f"Training trivial model for hour {hour}, quadrant {quadrant}. Only one class: {set(y)}.")
                        constant_class = y.iloc[0]  # Obtener la única clase
                        model_buffer[(hour, quadrant)] = lambda X_test: [constant_class] * len(X_test)  # Predicción constante
                        continue

                    X_train, _, y_train, _ = train_test_split(X, y, test_size=0.2, random_state=42)
                    model = LogisticRegression()
                    model.fit(X_train, y_train)

                    model_buffer[(hour, quadrant)] = model
        except Exception as e:
            logger.error(f"Error processing models: {e}")