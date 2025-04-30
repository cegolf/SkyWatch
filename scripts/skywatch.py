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
from env_vars_config import senderEmail, gatewayAddress, appKey, healthCheckEmail, csv_data_base_path
from aircraft_db import AircraftDatabase
from constants import MILITARY_CALLSIGNS, SQUAWK_MEANINGS
from alerting import send_health_check, send_email_alert
from util import load_watchlist, get_aircraft_data, get_weather_data, load_csv_data, clean_shutdown, clean_up_db
from plane_checks import check_possible_military_plane, check_squak, check_watchlist
from logging_util import get_last_log_lines
import socket
import shutil
from logging.handlers import TimedRotatingFileHandler
program_start_time = None


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    filename='skywatch.log'
)
logger = logging.getLogger('skywatch')

def configure_logger():
    """Configure the logger to use a TimedRotatingFileHandler."""
    log_file = 'skywatch.log'
    archive_folder = 'log_archive'  # Folder to store archived logs
    os.makedirs(archive_folder, exist_ok=True)  # Ensure the folder exists

    # Create a TimedRotatingFileHandler
    handler = TimedRotatingFileHandler(
        log_file,
        when='midnight',  # Rotate logs at midnight
        interval=1,       # Rotate every 1 day
        backupCount=30    # Keep the last 30 log files
    )
    handler.suffix = "%Y-%m-%d"  # Add date suffix to archived logs
    handler.extMatch = r"^\d{4}-\d{2}-\d{2}$"  # Match the date format for old logs

    # Move old logs to the archive folder
    def rename_log_file(source, dest):
        dest = os.path.join(archive_folder, os.path.basename(dest))
        shutil.move(source, dest)

    handler.namer = rename_log_file

    # Configure the logger
    logger = logging.getLogger('skywatch')
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)

    # Remove existing handlers and add the new one
    for existing_handler in logger.handlers[:]:
        logger.removeHandler(existing_handler)
        existing_handler.close()
    logger.addHandler(handler)

    return logger

# Replace the global logger configuration
logger = configure_logger()


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
        if (current_time > (LAST_SENT_HEALTH_CHECK + 3600)):
            logger.info("Sending health check")
            send_health_check(logger, db)
            LAST_SENT_HEALTH_CHECK = current_time
        time.sleep(30)
        # End Main Methode

def handle_exit_signal(sig, frame):
    """Handle termination signals and log program exit information"""
    signal_names = {
        signal.SIGINT: "SIGINT (Ctrl+C)",
        signal.SIGTERM: "SIGTERM",
    }
    
    signal_name = signal_names.get(sig, f"Signal {sig}")
    
    # Get the user and IP address
    user = os.getenv("USER", "Unknown User")
    user = os.getenv("USER", "Unknown User")
    try:
        logger.info(f"User: {user}")
        logger.info(f"SSH client details: {os.getenv('SSH_CLIENT')}")
        logger.info(f"SSH connection details: {os.getenv('SSH_CONNECTION')}")
        # Check for SSH connection details
        ssh_connection = os.getenv("SSH_CLIENT") or os.getenv("SSH_CONNECTION")
        logger.info(f"SSH connection details: {ssh_connection}")
        if ssh_connection:
            ip_address = ssh_connection.split()[0]  # Extract the IP address from the SSH connection string
        else:
            # Fallback to hostname resolution if no SSH connection is found
            hostname = socket.gethostname()
            ip_address = socket.gethostbyname(hostname)
    except Exception as e:
        ip_address = f"Unknown IP (Error: {str(e)})"


    # Calculate uptime
    now = datetime.now()
    uptime = now - program_start_time
    
    # Log the termination
    logger.info(f"Program terminated by {signal_name}. Total uptime: {uptime}")
    logger.info(f"Termination initiated by user: {user}, IP address: {ip_address}")
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
            f"Initiated by User: {user}\n"
            f"IP Address: {ip_address}\n"
            f"Last 10 log entries:\n"
            f"------------------\n"
            f"{last_logs}"
        )
        send_email_alert(healthCheckEmail, "SkyWatch Terminated", termination_message)
        logger.info("Termination notification email sent")
        clean_shutdown(logger)
    except Exception as e:
        logger.error(f"Failed to send termination notification: {str(e)}")
    finally:
        # Exit the program
        sys.exit(0)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.error(f"Unhandled exception: {str(e)}", exc_info=True)
        sys.exit(1)
