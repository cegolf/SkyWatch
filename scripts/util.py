import csv
import logging
import requests
from env_vars_config import healthCheckEmail, openWeatherApiKey
def load_watchlist():
    watchlist = {}
    with open("../watchlist.txt", "r") as file:
        for line in file:
            parts = line.split(':', 1)
            if len(parts) == 2:
                hex_code = parts[0].strip().upper()
                label = parts[1].strip()
                watchlist[hex_code] = label
    return watchlist

def get_aircraft_data():
    url = "http://adsbexchange.local/tar1090/data/aircraft.json"
    response = requests.get(url)
    data = response.json()
    return data['aircraft']

def load_csv_data(filename):
    csv_data = {}
    with open(filename, "r") as file:
        reader = csv.DictReader(file)
        for row in reader:
            hex_code = row['$ICAO']
            csv_data[hex_code] = row
    return csv_data

def clean_shutdown(logger):
    """Perform cleanup operations before shutting down"""
    logger.info("Performing clean shutdown...")
    
    # Close database connections
    try:
        # Your database cleanup code here
        # db.close_connection()
        logger.info("Database connections closed")
    except Exception as e:
        logger.error(f"Error during database cleanup: {str(e)}")
    
    # Any other cleanup operations
    logger.info("Cleanup completed")

def get_weather_data(latitude: float, longitude: float) -> dict:
    """Get current weather data from OpenWeatherMap API"""
    # You'll need to get an API key from OpenWeatherMap and set it here
    API_KEY = openWeatherApiKey
    url = f"https://api.openweathermap.org/data/2.5/weather?lat={latitude}&lon={longitude}&appid={API_KEY}&units=metric"
    
    try:
        response = requests.get(url)
        data = response.json()
        
        return {
            'temperature': data['main']['temp'],
            'wind_speed': data['wind']['speed'],
            'wind_direction': data['wind']['deg'],
            'visibility': data.get('visibility', 10000) / 1000,  # Convert to km
            'precipitation': data.get('rain', {}).get('1h', 0),
            'pressure': data['main']['pressure']
        }
    except Exception as e:
        logger.error(f"Error fetching weather data: {e}")
        return {}

def clean_up_db(logger,db):
    logger.info("Running database cleanup and archiving...")
    try:
        # Backup database before cleanup
        backup_path = db.backup_database()
        logger.info(f"Database backed up to: {backup_path}")
        
        # Archive old records
        db.archive_old_records(days_old=ARCHIVE_DAYS)
        
        # Vacuum database to reclaim space
        db.vacuum_database()
        
        # Get and print database stats
        stats = db.get_database_stats()
        logger.info("\nDatabase Statistics:")
        logger.info(f"Current sightings: {stats['aircraft_sightings_count']}")
        logger.info(f"Archived sightings: {stats['archived_aircraft_sightings_count']}")
        logger.info(f"Database size: {stats['database_size_mb']:.2f} MB")
        
    except Exception as e:
        logger.info(f"Error during cleanup: {e}")
        # Send alert about cleanup failure
        error_message = f"Database cleanup failed: {str(e)}"
        # send_email_alert(healthCheckEmail, "Database Cleanup Error", error_message)