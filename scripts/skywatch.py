import requests
import time
import csv
import smtplib
import os
import pytz
import psutil
import logging
import signal
import sys
from datetime import datetime, timedelta
from collections import deque
from env_vars_config import senderEmail, gatewayAddress, appKey, healthCheckEmail, openWeatherApiKey, csv_data_base_path
from aircraft_db import AircraftDatabase
from constants import MILITARY_CALLSIGNS, SQUAWK_MEANINGS
from alerting import send_health_check, send_email_alert
from util import load_watchlist, get_aircraft_data, get_weather_data, load_csv_data, clean_shutdown, clean_up_db
from plane_checks import check_possible_military_plane, check_squak, check_watchlist
from logging_util import get_last_log_lines
program_start_time = None

LAST_SENT_HEALTH_CHECK = 0


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    filename='skywatch.log'
)
logger = logging.getLogger('skywatch')


def main():
    # Log program start
    logger.info(f"SkyWatch program started on PID : {os.getpid()} and process {psutil.Process(os.getpid())}")
    global program_start_time
    program_start_time = datetime.now()
    
    # Register signal handlers
    signal.signal(signal.SIGINT, handle_exit_signal)
    signal.signal(signal.SIGTERM, handle_exit_signal)


    csv_files = [f"{csv_data_base_path}/plane-alert-civ-images.csv", f"{csv_data_base_path}/plane-alert-mil-images.csv", f"{csv_data_base_path}/plane-alert-gov-images.csv"]
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

    
    
    # Send startup health check
    send_health_check(logger,db, "SkyWatch Program Started", include_startup_info=True)

    while True:
        logger.debug("Main loop running...")
        current_time = int(time.time())
        
        # Rest of your code...
        
        # Run cleanup and archiving every 24 hours
        if current_time > (LAST_CLEANUP + CLEANUP_INTERVAL):
            clean_up_db(logger, db)
            LAST_CLEANUP = current_time

        aircraft_data = get_aircraft_data()
        
        # Record weather data periodically (every 5 minutes)
        if current_time % 300 == 0:  # Every 5 minutes
            logger.info("Recording weather data...")
            # Get weather data for your location (you'll need to set these coordinates)
            weather_data = get_weather_data(40.121026, -82.949669) 
            if weather_data:
                db.record_weather(weather_data)
        # Refactored loop
        logger.debug(f"Currently tracking {len(aircraft_data)} aircraft. Processing aircraft data...")
        for aircraft in aircraft_data:
            logger.debug(f"Processing aircraft: {aircraft}")
            hex_code = aircraft['hex'].upper()
            flight = aircraft.get('flight', '').strip().upper()
            squawk = aircraft.get('squawk', '')

            # Check for military callsign
            check_possible_military_plane(flight, logger, hex_code, aircraft, squawk, csv_data)
            
            # Record the aircraft sighting
            aircraft_record = aircraft.copy()
            if hex_code in csv_data:
                aircraft_record.update(csv_data[hex_code])
            db.record_sighting(aircraft_record)


            check_squak(logger, hex_code, aircraft, squawk, csv_data)

            check_watchlist(flight,csv_data, hex_code, aircraft)



        if current_time > (LAST_SENT_HEALTH_CHECK + 10800):
            logger.info("Sending health check")
            send_health_check(logger, db)
        time.sleep(30)
        # End Main Methode

def handle_exit_signal(sig, frame):
    """Handle termination signals and log program exit information"""
    signal_names = {
        signal.SIGINT: "SIGINT (Ctrl+C)",
        signal.SIGTERM: "SIGTERM",
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
        clean_shutdown(logger)
    except Exception as e:
        logger.error(f"Failed to send termination notification: {str(e)}")
    
    # Exit the program
    sys.exit(0)

if __name__ == "__main__":
    main()
