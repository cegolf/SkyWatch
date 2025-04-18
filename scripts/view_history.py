import argparse
from aircraft_db import AircraftDatabase
import datetime
import pytz
from tabulate import tabulate

def format_timestamp(timestamp_str):
    """Format timestamp for display"""
    dt = datetime.datetime.fromisoformat(timestamp_str)
    local_tz = pytz.timezone('America/New_York')
    local_dt = dt.astimezone(local_tz)
    return local_dt.strftime('%Y-%m-%d %H:%M:%S %Z')

def main():
    parser = argparse.ArgumentParser(description='View aircraft sighting history')
    parser.add_argument('--hex', help='Filter by hex code')
    parser.add_argument('--days', type=int, default=7, help='Number of days to look back')
    parser.add_argument('--limit', type=int, default=50, help='Maximum number of records to show')
    
    args = parser.parse_args()
    
    db = AircraftDatabase()
    
    # Calculate date range
    end_date = datetime.datetime.now(pytz.UTC)
    start_date = end_date - datetime.timedelta(days=args.days)
    
    # Get sightings
    sightings = db.get_sightings(
        hex_code=args.hex,
        start_date=start_date,
        end_date=end_date,
        limit=args.limit
    )
    
    if not sightings:
        print("No sightings found matching the criteria.")
        return
    
    # Prepare data for tabulate
    table_data = []
    for sighting in sightings:
        table_data.append([
            format_timestamp(sighting['timestamp']),
            sighting['hex_code'],
            sighting['flight_number'] or 'N/A',
            sighting['altitude'] or 'N/A',
            sighting['ground_speed'] or 'N/A',
            sighting['operator'] or 'N/A',
            sighting['aircraft_type'] or 'N/A'
        ])
    
    headers = ['Timestamp', 'Hex Code', 'Flight', 'Altitude', 'Speed', 'Operator', 'Type']
    print(tabulate(table_data, headers=headers, tablefmt='grid'))
    
    # Print summary
    unique_aircraft = len(set(s['hex_code'] for s in sightings))
    print(f"\nSummary:")
    print(f"Total sightings: {len(sightings)}")
    print(f"Unique aircraft: {unique_aircraft}")

if __name__ == "__main__":
    main() 