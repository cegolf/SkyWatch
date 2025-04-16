import requests
import fnmatch
import time
import csv
import smtplib
from email.message import EmailMessage
from emailToSMSConfig import senderEmail, gatewayAddress, appKey, healthCheckEmail, openWeatherApiKey
import os
import pytz
from aircraft_db import AircraftDatabase
import json
import psutil  # You'll need to install this package
import logging
from datetime import datetime, timedelta
import signal
from collections import deque
import sys

# Global variables to track start time
program_start_time = None

# Enter in your Bot Token and the Chat ID of the chat you want the alerts sent to.
TELEGRAM_BOT_TOKEN = ""
TELEGRAM_CHAT_ID = ""

LAST_SENT_HEALTH_CHECK = int(time.time())

# Add or remove these as needed
SQUAWK_MEANINGS = {
    "7500": "Aircraft Hijacking",
    "7600": "Radio Failure",
    "7700": "Emergency",
    "5000": "NORAD",
    "5400": "NORAD",
    "6100": "NORAD",
    "6400": "NORAD",
    "7777": "Millitary intercept",
    "0000": "discrete VFR operations",
    "1277": "Search & Rescue"
}
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    filename='skywatch.log'
)
logger = logging.getLogger('skywatch')

# Constants
HEALTH_CHECK_INTERVAL = 3600  # 1 hour in seconds

def send_health_check(db,subject_prefix="SkyWatch Health Check Report", include_startup_info=False):
    """Send a detailed health check email with system and application statistics"""
    # print("Sending Health Check...")
    try:
        pid = os.getpid()
        process = psutil.Process(pid)
        
        # System stats
        cpu_percent = psutil.cpu_percent()
        memory_info = process.memory_info()
        memory_percent = process.memory_percent()
        
        # Time information - Fix the timezone issue
        now = time.time()
        local_tz = pytz.timezone('America/New_York')
        now_local = datetime.now(local_tz)
        
        # Make start_time timezone-aware by localizing it to the same timezone
        start_time_naive = datetime.fromtimestamp(process.create_time())
        start_time = local_tz.localize(start_time_naive)
        
        # Now both are timezone-aware, subtraction works
        uptime = now_local - start_time
        
        # Application stats
        aircraft_data = get_aircraft_data()
        aircraft_count = len(aircraft_data)
        
        # Database stats
        recent_sightings = db.get_sightings(limit=1000)
        unique_aircraft = len(set(s['hex_code'] for s in recent_sightings))
        stats = db.get_database_stats()
        
        # # Alert statistics
        # watchlist_alerts = len(watchlist_alert_history)
        # squawk_alerts = len(squawk_alert_history)
        
        # Format email message
        healthCheckMessage = (
            f"{subject_prefix}\n"
            f"{'=' * len(subject_prefix)}\n\n"
            f"Time: {now_local}\n"
            f"Process ID: {pid}\n"
            f"Uptime: {uptime}\n\n"
        )
        
        if include_startup_info:
            healthCheckMessage += (
                f"Startup Information:\n"
                f"  Python Version: {sys.version.split()[0]}\n"
                f"  Host: {os.uname().nodename}\n"
                f"  Working Directory: {os.getcwd()}\n\n"
            )
        
        healthCheckMessage += (
            f"System Resources:\n"
            f"  CPU Usage: {cpu_percent}%\n"
            f"  Memory Usage: {memory_info.rss / (1024 * 1024):.2f} MB ({memory_percent:.2f}%)\n\n"
            f"Aircraft Statistics:\n"
            f"  Aircraft Currently Tracking: {aircraft_count}\n"
            f"  Unique Aircraft Spotted (last 1000 records): {unique_aircraft}\n\n"
            # f"Alert Statistics (last 24 hours):\n"
            # f"  Watchlist Alerts: {watchlist_alerts}\n"
            # f"  Squawk Alerts: {squawk_alerts}\n\n"
            f"Database Statistics:\n"
            f"  Current sightings: {stats['aircraft_sightings_count']}\n"
            f"  Archived sightings: {stats['archived_aircraft_sightings_count']}\n"
            f"  Database size: {stats['database_size_mb']:.2f} MB\n"
        )
        
        send_email_alert(healthCheckEmail, subject_prefix, healthCheckMessage)
        logger.info("Health check email sent successfully")
        
        # Update the last health check timestamp
        global LAST_SENT_HEALTH_CHECK
        LAST_SENT_HEALTH_CHECK = int(time.time())
        
    except Exception as e:
        # print(f"exception : {e}")
        logger.error(f"Failed to send health check email: {str(e)}")


def send_email_alert(email, subject, content):
    msg = EmailMessage()
    msg.set_content(content)

    msg['From'] = senderEmail
    msg['To'] = email
    msg['Subject'] =subject

    server = smtplib.SMTP('smtp.gmail.com', 587)
    server.starttls()
    server.login(senderEmail, appKey)

    server.send_message(msg)
    server.quit()

def load_watchlist():
    watchlist = {}
    with open("watchlist.txt", "r") as file:
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




def clean_shutdown():
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



def main():
    # Log program start
    logger.info(f"SkyWatch program started on PID : {os.getpid()} and process {psutil.Process(os.getpid())}")
    global program_start_time
    program_start_time = datetime.now()
    
    # Register signal handlers
    signal.signal(signal.SIGINT, handle_exit_signal)
    signal.signal(signal.SIGTERM, handle_exit_signal)
    signal.signal(signal.SIGHUP, handle_exit_signal)
    squawk_alert_history = {}
    watchlist_alert_history = {}
    csv_files = ["plane-alert-civ-images.csv", "plane-alert-mil-images.csv", "plane-alert-gov-images.csv"]
    csv_data = {}
    
    # Initialize the database
    db = AircraftDatabase()
    
    # Track last cleanup time
    LAST_CLEANUP = int(time.time())
    CLEANUP_INTERVAL = 86400  # 24 hours in seconds
    ARCHIVE_DAYS = 30  # Archive records older than 30 days

    # Initialize LAST_SENT_HEALTH_CHECK to trigger immediate health check
    global LAST_SENT_HEALTH_CHECK
    # Setting to 0 ensures the health check condition will be true immediately
    LAST_SENT_HEALTH_CHECK = 0  

    for filename in csv_files:
        csv_data.update(load_csv_data(filename))

    watchlist = load_watchlist()
    
    # Send startup health check
    # Send startup health check
    send_health_check(db, "SkyWatch Program Started", include_startup_info=True)

    while True:
        current_time = int(time.time())
        
        # Rest of your code...
        
        # Run cleanup and archiving every 24 hours
        if current_time > (LAST_CLEANUP + CLEANUP_INTERVAL):
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
                
                LAST_CLEANUP = current_time
            except Exception as e:
                logger.info(f"Error during cleanup: {e}")
                # Send alert about cleanup failure
                error_message = f"Database cleanup failed: {str(e)}"
                send_email_alert(healthCheckEmail, "Database Cleanup Error", error_message)

        aircraft_data = get_aircraft_data()
        
        # Record weather data periodically (every 5 minutes)
        if current_time % 300 == 0:  # Every 5 minutes
            # Get weather data for your location (you'll need to set these coordinates)
            weather_data = get_weather_data(40.7128, -74.0060)  # Example: New York City coordinates
            if weather_data:
                db.record_weather(weather_data)

        for aircraft in aircraft_data:
            hex_code = aircraft['hex'].upper()
            flight = aircraft.get('flight', '').strip().upper()
            squawk = aircraft.get('squawk', '')
            
            # Record the aircraft sighting
            aircraft_record = aircraft.copy()
            if hex_code in csv_data:
                aircraft_record.update(csv_data[hex_code])
            db.record_sighting(aircraft_record)

            # Alert on specific squawk codes
            if squawk in SQUAWK_MEANINGS and (
                    hex_code not in squawk_alert_history or time.time() - squawk_alert_history[hex_code] >= 3600):
                logger.info("SQUAK MATCH")
                squawk_alert_history[hex_code] = time.time()
                squawk_meaning = SQUAWK_MEANINGS[squawk]

                if hex_code in csv_data:
                    context = csv_data[hex_code]
                    message = (
                        f"Squawk Alert!\nHex: {hex_code}\nSquawk: {squawk} ({squawk_meaning})\n"
                        f"Flight: {aircraft.get('flight', 'N/A')}\nAltitude: {aircraft.get('alt_geom', 'N/A')} ft\n"
                        f"Ground Speed: {aircraft.get('gs', 'N/A')} knots\nTrack: {aircraft.get('track', 'N/A')}\n"
                        f"Operator: {context.get('$Operator', 'N/A')}\nType: {context.get('$Type', 'N/A')}\n"
                        f"Image: {context.get('#ImageLink', 'N/A')}"
                    )
                else:
                    message = (
                        f"Squawk Alert!\nHex: {hex_code}\nSquawk: {squawk} ({squawk_meaning})\n"
                        f"Flight: {aircraft.get('flight', 'N/A')}\nAltitude: {aircraft.get('alt_geom', 'N/A')} ft\n"
                        f"Ground Speed: {aircraft.get('gs', 'N/A')} knots\nTrack: {aircraft.get('track', 'N/A')}"
                    )
                send_email_alert(gatewayAddress, "SQUAWK ALERT!", message)

            # Alert on items in the watchlist
            for entry in watchlist:
                if entry.endswith('*'):
                    if fnmatch.fnmatch(flight, entry):
                        if (hex_code not in watchlist_alert_history or
                                time.time() - watchlist_alert_history[hex_code] >= 3600):
                            watchlist_alert_history[hex_code] = time.time()
                            if hex_code in csv_data:
                                context = csv_data[hex_code]
                                message = (
                                    f"Watchlist Alert!\n"
                                    f"Hex: {hex_code}\n"
                                    f"Label: {watchlist[entry]}\n"
                                    f"Flight: {aircraft.get('flight', 'N/A')}\n"
                                    f"Altitude: {aircraft.get('alt_geom', 'N/A')} ft\n"
                                    f"Ground Speed: {aircraft.get('gs', 'N/A')} knots\n"
                                    f"Track: {aircraft.get('track', 'N/A')}\n"
                                    f"Operator: {context.get('$Operator', 'N/A')}\n"
                                    f"Type: {context.get('$Type', 'N/A')}\n"
                                    f"Image: {context.get('#ImageLink', 'N/A')}"
                                )
                            else:
                                message = (
                                    f"Watchlist Alert!\n"
                                    f"Hex: {hex_code}\n"
                                    f"Label: {watchlist[entry]}\n"
                                    f"Flight: {aircraft.get('flight', 'N/A')}\n"
                                    f"Altitude: {aircraft.get('alt_geom', 'N/A')} ft\n"
                                    f"Ground Speed: {aircraft.get('gs', 'N/A')} knots\n"
                                    f"Track: {aircraft.get('track', 'N/A')}"
                                )
                            send_email_sms(message)
                elif hex_code == entry or flight == entry:
                    if hex_code not in watchlist_alert_history or time.time() - watchlist_alert_history[hex_code] >= 3600:
                        watchlist_alert_history[hex_code] = time.time()
                        if hex_code in csv_data:
                            context = csv_data[hex_code]
                            message = (
                                f"Watchlist Alert!\n"
                                f"Hex: {hex_code}\n"
                                f"Label: {watchlist[entry]}\n"
                                f"Flight: {aircraft.get('flight', 'N/A')}\n"
                                f"Altitude: {aircraft.get('alt_geom', 'N/A')} ft\n"
                                f"Ground Speed: {aircraft.get('gs', 'N/A')} knots\n"
                                f"Track: {aircraft.get('track', 'N/A')}\n"
                                f"Operator: {context.get('$Operator', 'N/A')}\n"
                                f"Type: {context.get('$Type', 'N/A')}\n"
                                f"Image: {context.get('#ImageLink', 'N/A')}"
                            )
                        else:
                            message = (
                                f"Watchlist Alert!\nHex: {hex_code}\n"
                                f"Label: {watchlist[entry]}\n"
                                f"Flight: {aircraft.get('flight', 'N/A')}\n"
                                f"Altitude: {aircraft.get('alt_geom', 'N/A')} ft\n"
                                f"Ground Speed: {aircraft.get('gs', 'N/A')} knots\n"
                                f"Track: {aircraft.get('track', 'N/A')}"
                            )
                        send_email_alert(gatewayAddress, "WATCHLIST ALERT!", message)

        if current_time > (LAST_SENT_HEALTH_CHECK + 10800):
            logger.info("Sending health check")
            send_health_check(db)
        time.sleep(30)
        # End Main Methode





def get_last_log_lines(log_file, num_lines=10):
    """Get the last N lines from a log file"""
    try:
        # Method that works for both small and large files
        with open(log_file, 'r') as file:
            # Use a deque with maxlen to efficiently get the last N lines
            from collections import deque
            last_lines = deque(maxlen=num_lines)
            
            for line in file:
                last_lines.append(line.strip())
            
            return '\n'.join(last_lines)
    except Exception as e:
        return f"Error reading log file: {str(e)}"
def handle_exit_signal(sig, frame):
    """Handle termination signals and log program exit information"""
    signal_names = {
        signal.SIGINT: "SIGINT (Ctrl+C)",
        signal.SIGTERM: "SIGTERM",
        # signal.SIGHUP: "SIGHUP",
    }
    
    signal_name = signal_names.get(sig, f"Signal {sig}")
    
    # Calculate uptime
    now = datetime.now()
    uptime = now - program_start_time
    
    # Log the termination
    logger.info(f"Program terminated by {signal_name}. Total uptime: {uptime}")

    # Get the last 10 log lines
    last_logs = get_last_log_lines('skywatch.log', 10)
    
    # Optional: Send an email notification about the termination
    try:
        termination_message = (
            f"SkyWatch Terminated\n"
            f"==================\n\n"
            f"Time: {now}\n"
            f"Termination Signal: {signal_name}\n"
            f"Total Uptime: {uptime}\n"
            f"Last 10 log entries:\n"
            f"------------------\n"
            f"{last_logs}"
        )
        send_email_alert(healthCheckEmail, "SkyWatch Terminated", termination_message)
        logger.info("Termination notification email sent")
        clean_shutdown()
    except Exception as e:
        logger.error(f"Failed to send termination notification: {str(e)}")
    
    # Exit the program
    sys.exit(0)

if __name__ == "__main__":
    main()
