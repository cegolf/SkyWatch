import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from aircraft_db import AircraftDatabase
import joblib
import datetime
import pytz
from typing import Dict, List, Tuple

class FlightPredictor:
    def __init__(self, model_path: str = "flight_predictor_model.joblib"):
        self.model_path = model_path
        self.scaler = StandardScaler()
        self.model = None
        self.db = AircraftDatabase()
        
    def prepare_training_data(self) -> Tuple[pd.DataFrame, pd.Series]:
        """Prepare training data from historical records"""
        # Get all sightings and weather data
        sightings = self.db.get_sightings(limit=10000)  # Adjust limit as needed
        weather_data = self._get_weather_data()
        
        # Convert to DataFrames
        df_sightings = pd.DataFrame(sightings)
        df_weather = pd.DataFrame(weather_data)
        
        # Convert timestamps to datetime
        df_sightings['timestamp'] = pd.to_datetime(df_sightings['timestamp'])
        df_weather['timestamp'] = pd.to_datetime(df_weather['timestamp'])
        
        # Merge weather data with sightings
        df = pd.merge_asof(
            df_sightings.sort_values('timestamp'),
            df_weather.sort_values('timestamp'),
            on='timestamp',
            direction='nearest'
        )
        
        # Calculate features
        features = []
        targets = []
        
        for hex_code in df['hex_code'].unique():
            hex_data = df[df['hex_code'] == hex_code].sort_values('timestamp')
            
            if len(hex_data) < 2:
                continue
                
            # Calculate speed changes and delays
            for i in range(1, len(hex_data)):
                prev_row = hex_data.iloc[i-1]
                curr_row = hex_data.iloc[i]
                
                time_diff = (curr_row['timestamp'] - prev_row['timestamp']).total_seconds() / 3600  # hours
                speed_diff = curr_row['ground_speed'] - prev_row['ground_speed']
                
                # Create feature vector
                feature_vector = [
                    prev_row['altitude'],
                    prev_row['ground_speed'],
                    prev_row['temperature'],
                    prev_row['wind_speed'],
                    prev_row['wind_direction'],
                    prev_row['visibility'],
                    prev_row['precipitation'],
                    prev_row['pressure']
                ]
                
                features.append(feature_vector)
                targets.append(speed_diff)  # Predict speed change
                
        return np.array(features), np.array(targets)
    
    def _get_weather_data(self) -> List[Dict]:
        """Get historical weather data from database"""
        # This would be implemented based on your database structure
        # For now, returning empty list as placeholder
        return []
    
    def train(self):
        """Train the prediction model"""
        X, y = self.prepare_training_data()
        
        if len(X) == 0:
            print("Not enough data to train the model")
            return
            
        # Scale features
        X_scaled = self.scaler.fit_transform(X)
        
        # Split data
        X_train, X_test, y_train, y_test = train_test_split(
            X_scaled, y, test_size=0.2, random_state=42
        )
        
        # Train model
        self.model = RandomForestRegressor(n_estimators=100, random_state=42)
        self.model.fit(X_train, y_train)
        
        # Evaluate
        train_score = self.model.score(X_train, y_train)
        test_score = self.model.score(X_test, y_test)
        
        print(f"Training R² score: {train_score:.3f}")
        print(f"Testing R² score: {test_score:.3f}")
        
        # Save model
        joblib.dump((self.model, self.scaler), self.model_path)
    
    def load_model(self):
        """Load trained model from file"""
        try:
            self.model, self.scaler = joblib.load(self.model_path)
        except FileNotFoundError:
            print("Model file not found. Please train the model first.")
    
    def predict(self, current_conditions: Dict) -> float:
        """Predict speed change based on current conditions"""
        if self.model is None:
            self.load_model()
            
        if self.model is None:
            return 0.0
            
        # Prepare feature vector
        feature_vector = [
            current_conditions['altitude'],
            current_conditions['ground_speed'],
            current_conditions['temperature'],
            current_conditions['wind_speed'],
            current_conditions['wind_direction'],
            current_conditions['visibility'],
            current_conditions['precipitation'],
            current_conditions['pressure']
        ]
        
        # Scale features and predict
        X_scaled = self.scaler.transform([feature_vector])
        prediction = self.model.predict(X_scaled)[0]
        
        return prediction

def main():
    predictor = FlightPredictor()
    
    # Train or load model
    try:
        predictor.load_model()
    except FileNotFoundError:
        print("Training new model...")
        predictor.train()
    
    # Example prediction
    current_conditions = {
        'altitude': 30000,
        'ground_speed': 450,
        'temperature': 20,
        'wind_speed': 15,
        'wind_direction': 90,
        'visibility': 10,
        'precipitation': 0,
        'pressure': 1013
    }
    
    prediction = predictor.predict(current_conditions)
    print(f"Predicted speed change: {prediction:.1f} knots")
    
    if prediction < -50:
        print("Warning: Significant speed reduction predicted")
    elif prediction > 50:
        print("Warning: Significant speed increase predicted")

if __name__ == "__main__":
    main() 