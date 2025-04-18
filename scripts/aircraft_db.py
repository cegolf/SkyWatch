import sqlite3
import datetime
import pytz
from typing import Dict, List, Optional
import os
import shutil

class AircraftDatabase:
    def __init__(self, db_path: str = "../db/aircraft_history.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Initialize the database with required tables"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Create aircraft sightings table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS aircraft_sightings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    hex_code TEXT NOT NULL,
                    flight_number TEXT,
                    altitude INTEGER,
                    ground_speed INTEGER,
                    track REAL,
                    operator TEXT,
                    aircraft_type TEXT,
                    image_url TEXT,
                    timestamp DATETIME NOT NULL,
                    latitude REAL,
                    longitude REAL,
                    squawk_code TEXT,
                    UNIQUE(hex_code, timestamp)
                )
            ''')
            
            # Create archived aircraft sightings table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS archived_aircraft_sightings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    hex_code TEXT NOT NULL,
                    flight_number TEXT,
                    altitude INTEGER,
                    ground_speed INTEGER,
                    track REAL,
                    operator TEXT,
                    aircraft_type TEXT,
                    image_url TEXT,
                    timestamp DATETIME NOT NULL,
                    latitude REAL,
                    longitude REAL,
                    squawk_code TEXT,
                    archive_date DATETIME NOT NULL
                )
            ''')
            
            # Create weather conditions table for ML feature
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS weather_conditions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME NOT NULL,
                    temperature REAL,
                    wind_speed REAL,
                    wind_direction REAL,
                    visibility REAL,
                    precipitation REAL,
                    pressure REAL,
                    UNIQUE(timestamp)
                )
            ''')
            
            # Create archived weather conditions table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS archived_weather_conditions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME NOT NULL,
                    temperature REAL,
                    wind_speed REAL,
                    wind_direction REAL,
                    visibility REAL,
                    precipitation REAL,
                    pressure REAL,
                    archive_date DATETIME NOT NULL
                )
            ''')
            
            conn.commit()

    def archive_old_records(self, days_old: int = 30, batch_size: int = 1000):
        """
        Archive records older than specified days to archive tables
        and then delete them from the main tables.
        
        Args:
            days_old: Number of days after which records should be archived
            batch_size: Number of records to process in each batch
        """
        cutoff_date = datetime.datetime.now(pytz.UTC) - datetime.timedelta(days=days_old)
        archive_date = datetime.datetime.now(pytz.UTC)
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Archive aircraft sightings
            while True:
                # Get batch of old records
                cursor.execute('''
                    SELECT * FROM aircraft_sightings 
                    WHERE timestamp < ? 
                    LIMIT ?
                ''', (cutoff_date, batch_size))
                
                old_records = cursor.fetchall()
                if not old_records:
                    break
                
                # Archive the records
                cursor.executemany('''
                    INSERT INTO archived_aircraft_sightings 
                    (hex_code, flight_number, altitude, ground_speed, track, 
                     operator, aircraft_type, image_url, timestamp, latitude, 
                     longitude, squawk_code, archive_date)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', [(*record[1:], archive_date) for record in old_records])
                
                # Delete the archived records
                cursor.execute('''
                    DELETE FROM aircraft_sightings 
                    WHERE id IN ({})
                '''.format(','.join('?' * len(old_records))), 
                [record[0] for record in old_records])
                
                conn.commit()
            
            # Archive weather conditions
            while True:
                cursor.execute('''
                    SELECT * FROM weather_conditions 
                    WHERE timestamp < ? 
                    LIMIT ?
                ''', (cutoff_date, batch_size))
                
                old_records = cursor.fetchall()
                if not old_records:
                    break
                
                cursor.executemany('''
                    INSERT INTO archived_weather_conditions 
                    (timestamp, temperature, wind_speed, wind_direction, 
                     visibility, precipitation, pressure, archive_date)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', [(*record[1:], archive_date) for record in old_records])
                
                cursor.execute('''
                    DELETE FROM weather_conditions 
                    WHERE id IN ({})
                '''.format(','.join('?' * len(old_records))), 
                [record[0] for record in old_records])
                
                conn.commit()

    def vacuum_database(self):
        """Run VACUUM to reclaim space and optimize the database"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("VACUUM")

    def backup_database(self, backup_path: str = None):
        """
        Create a backup of the database file.
        
        Args:
            backup_path: Path where backup should be saved. If None, 
                        creates backup in same directory with timestamp.
        """
        if backup_path is None:
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = f"aircraft_history_backup_{timestamp}.db"
        
        shutil.copy2(self.db_path, backup_path)
        return backup_path

    def get_database_stats(self) -> Dict:
        """Get statistics about the database"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            stats = {}
            
            # Get table sizes
            for table in ['aircraft_sightings', 'archived_aircraft_sightings', 
                         'weather_conditions', 'archived_weather_conditions']:
                cursor.execute(f'SELECT COUNT(*) FROM {table}')
                stats[f'{table}_count'] = cursor.fetchone()[0]
            
            # Get database size
            stats['database_size_mb'] = os.path.getsize(self.db_path) / (1024 * 1024)
            
            # Get date ranges
            for table in ['aircraft_sightings', 'archived_aircraft_sightings']:
                cursor.execute(f'''
                    SELECT MIN(timestamp), MAX(timestamp) 
                    FROM {table}
                ''')
                min_date, max_date = cursor.fetchone()
                stats[f'{table}_date_range'] = {
                    'min': min_date,
                    'max': max_date
                }
            
            return stats

    def record_sighting(self, aircraft_data: Dict):
        """Record an aircraft sighting in the database"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Get current timestamp in UTC
            timestamp = datetime.datetime.now(pytz.UTC)
            
            cursor.execute('''
                INSERT OR IGNORE INTO aircraft_sightings 
                (hex_code, flight_number, altitude, ground_speed, track, 
                 operator, aircraft_type, image_url, timestamp, latitude, 
                 longitude, squawk_code)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                aircraft_data.get('hex', '').upper(),
                aircraft_data.get('flight', ''),
                aircraft_data.get('alt_geom'),
                aircraft_data.get('gs'),
                aircraft_data.get('track'),
                aircraft_data.get('operator', ''),
                aircraft_data.get('type', ''),
                aircraft_data.get('image_url', ''),
                timestamp,
                aircraft_data.get('lat'),
                aircraft_data.get('lon'),
                aircraft_data.get('squawk', '')
            ))
            
            conn.commit()

    def get_sightings(self, 
                     hex_code: Optional[str] = None,
                     start_date: Optional[datetime.datetime] = None,
                     end_date: Optional[datetime.datetime] = None,
                     limit: int = 100) -> List[Dict]:
        """Query aircraft sightings with optional filters"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            query = "SELECT * FROM aircraft_sightings WHERE 1=1"
            params = []
            
            if hex_code:
                query += " AND hex_code = ?"
                params.append(hex_code.upper())
            
            if start_date:
                query += " AND timestamp >= ?"
                params.append(start_date)
            
            if end_date:
                query += " AND timestamp <= ?"
                params.append(end_date)
            
            query += " ORDER BY timestamp DESC LIMIT ?"
            params.append(limit)
            
            cursor.execute(query, params)
            columns = [description[0] for description in cursor.description]
            results = []
            
            for row in cursor.fetchall():
                results.append(dict(zip(columns, row)))
            
            return results

    def record_weather(self, weather_data: Dict):
        """Record weather conditions for ML feature"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            timestamp = datetime.datetime.now(pytz.UTC)
            
            cursor.execute('''
                INSERT OR IGNORE INTO weather_conditions
                (timestamp, temperature, wind_speed, wind_direction, 
                 visibility, precipitation, pressure)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                timestamp,
                weather_data.get('temperature'),
                weather_data.get('wind_speed'),
                weather_data.get('wind_direction'),
                weather_data.get('visibility'),
                weather_data.get('precipitation'),
                weather_data.get('pressure')
            ))
            
            conn.commit() 