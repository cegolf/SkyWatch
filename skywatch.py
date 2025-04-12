import requests
import fnmatch
import time
import csv
import smtplib
from email.message import EmailMessage
from emailToSMSConfig import senderEmail, gatewayAddress, appKey, healthCheckEmail, openWeatherApiKey
import os
import datetime
import pytz
from aircraft_db import AircraftDatabase
import json

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
    "1277": "Search & Rescue",
    '8698': "Chris's Birthday Squawk!!",
    '0331': "Yuki's Birthday Squawk!!"
}


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


def send_telegram_alert(message):
    telegram_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    params = {
        'chat_id': TELEGRAM_CHAT_ID,
        'text': message,
    }
    response = requests.get(telegram_url, params=params)
    return response.status_code


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
    API_KEY = "c038127b761f7ae6e713c24bdb753cbf "
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
        print(f"Error fetching weather data: {e}")
        return {}

def main():
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

    for filename in csv_files:
        csv_data.update(load_csv_data(filename))

    watchlist = load_watchlist()

    while True:
        current_time = int(time.time())
        
        # Run cleanup and archiving every 24 hours
        if current_time > (LAST_CLEANUP + CLEANUP_INTERVAL):
            print("Running database cleanup and archiving...")
            try:
                # Backup database before cleanup
                backup_path = db.backup_database()
                print(f"Database backed up to: {backup_path}")
                
                # Archive old records
                db.archive_old_records(days_old=ARCHIVE_DAYS)
                
                # Vacuum database to reclaim space
                db.vacuum_database()
                
                # Get and print database stats
                stats = db.get_database_stats()
                print("\nDatabase Statistics:")
                print(f"Current sightings: {stats['aircraft_sightings_count']}")
                print(f"Archived sightings: {stats['archived_aircraft_sightings_count']}")
                print(f"Database size: {stats['database_size_mb']:.2f} MB")
                
                LAST_CLEANUP = current_time
            except Exception as e:
                print(f"Error during cleanup: {e}")
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
                print("SQUAK MATCH")
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
                            # status_code = send_telegram_alert(message)
                            # if status_code == 200:
                            #     message_lines = message.split('\n')[:3]
                            #     for line in message_lines:
                            #         print(line)
                            # else:
                            #     print(f"Failed to send watchlist alert. Status Code: {status_code}")
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
            print("Sending Health Check")
            pid = int(os.getpid())
            now = time.time()
            datetime_object = datetime.datetime.fromtimestamp(now)
            now_local = datetime.datetime.now(pytz.timezone('America/New_York'))
            aircraft_count = len(aircraft_data)
            
            # Get recent sightings count and database stats
            recent_sightings = db.get_sightings(limit=1000)
            unique_aircraft = len(set(s['hex_code'] for s in recent_sightings))
            stats = db.get_database_stats()
            
            healthCheckMessage = (f"Health Check Alert \n Port : {pid}\n"
                            f"Time (Epoch Sec) : {now}\n"
                            f"Time (Formmatted EST) : {now_local} \n"
                            f"Aircraft Currently Tracking : {aircraft_count}\n"
                            f"Unique Aircraft Spotted (Last 1000 records): {unique_aircraft}\n"
                            f"Database Statistics:\n"
                            f"  Current sightings: {stats['aircraft_sightings_count']}\n"
                            f"  Archived sightings: {stats['archived_aircraft_sightings_count']}\n"
                            f"  Database size: {stats['database_size_mb']:.2f} MB\n")
            send_email_alert(healthCheckEmail, "Health Check Alert!", healthCheckMessage)
        time.sleep(30)


if __name__ == "__main__":
    main()
