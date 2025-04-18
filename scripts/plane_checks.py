import fnmatch
from constants import MILITARY_CALLSIGNS, SQUAWK_MEANINGS
from alerting import create_alert_message, send_email_alert
from util import load_watchlist
def check_possible_military_plane(flight, logger, hex_code, aircraft, squawk, csv_data):
    for mil_callsign in MILITARY_CALLSIGNS:
        if flight.startswith(mil_callsign):
            logMessage = create_alert_message(
                hex_code, 
                aircraft, 
                "Military Callsign", 
                f"Squawk: {squawk}", 
                csv_data.get(hex_code)
            )
            logger.info(f"Possible military callsign detected: {logMessage}")
            break

def check_squak(logger, hex_code, aircraft, squawk, csv_data):
    if squawk in SQUAWK_MEANINGS:
        logger.info("SQUAK MATCH")
        squawk_meaning = SQUAWK_MEANINGS[squawk]
        context = csv_data.get(hex_code)
        message = create_alert_message(
            hex_code, 
            aircraft, 
            "Squawk", 
            f"Squawk: {squawk} ({squawk_meaning})", 
            context
        )
        send_email_alert(gatewayAddress, "SQUAWK ALERT!", message)

def check_watchlist(flight,csv_data, hex_code, aircraft):
    watchlist = load_watchlist()
    for entry in watchlist:
        if entry.endswith('*'):
            if fnmatch.fnmatch(flight, entry):
                context = csv_data.get(hex_code)
                message = create_alert_message(
                    hex_code, 
                    aircraft, 
                    "Watchlist", 
                    f"Label: {watchlist[entry]}", 
                    context
                )
                send_email_alert(gatewayAddress, "Watchlist Match", message)
        elif hex_code == entry or flight == entry:
            context = csv_data.get(hex_code)
            message = create_alert_message(
                hex_code, 
                aircraft, 
                "Watchlist", 
                f"Label: {watchlist[entry]}", 
                context
            )
            send_email_alert(gatewayAddress, "Hex Match",message)