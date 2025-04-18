import time
import smtplib
import os
import pytz
import psutil
import logging
from datetime import datetime
from email.message import EmailMessage
from env_vars_config import senderEmail, gatewayAddress, appKey, healthCheckEmail
from util import get_aircraft_data
import sys

def send_health_check(logger,db,subject_prefix="SkyWatch Health Check Report", include_startup_info=False):
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
        logger.info(f"Health check email sent successfully with data {healthCheckMessage}")
        
        # Update the last health check timestamp
        global LAST_SENT_HEALTH_CHECK
        LAST_SENT_HEALTH_CHECK = int(time.time())
        
    except Exception as e:
        # print(f"exception : {e}")
        logger.error(f"Failed to send health check email: {str(e)}")

def create_alert_message(hex_code, aircraft, alert_type, alert_detail, context=None):
    """Generate alert message for squawk or watchlist alerts."""
    base_message = (
        f"{alert_type} Alert!\n"
        f"Hex: {hex_code}\n"
        f"{alert_detail}\n"
        f"Flight: {aircraft.get('flight', 'N/A')}\n"
        f"Altitude: {aircraft.get('alt_geom', 'N/A')} ft\n"
        f"Ground Speed: {aircraft.get('gs', 'N/A')} knots\n"
        f"Track: {aircraft.get('track', 'N/A')}"
        f"\nLatitude: {aircraft.get('lat', 'N/A')}\n"
        f"Longitude: {aircraft.get('lon', 'N/A')}\n"
    )
    if context:
        base_message += (
            f"\nOperator: {context.get('$Operator', 'N/A')}\n"
            f"Type: {context.get('$Type', 'N/A')}\n"
            f"Image: {context.get('#ImageLink', 'N/A')}"
        )
    return base_message

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