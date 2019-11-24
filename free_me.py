import argparse
import datetime
from datetime import timezone
import pickle
import os.path
from collections import namedtuple
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

Time = namedtuple("Time", "time is_start busy pot_free")

# If modifying these scopes, delete the file token.pickle.
SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']

def get_busy_times(calendars, days=7, buf=10):
    """Shows basic usage of the Google Calendar API.
    Prints the start and name of the next 10 events on the user's calendar.
    """
    creds = None
    # The file token.pickle stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first
    # time.
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        with open('token.pickle', 'wb') as token:
            pickle.dump(creds, token)

    service = build('calendar', 'v3', credentials=creds)

    # Call the Calendar API
    days = datetime.timedelta(days=days)
    now = datetime.datetime.utcnow().isoformat() + 'Z' # 'Z' indicates UTC time
    end = (datetime.datetime.utcnow() + days).isoformat() + 'Z'
    cals = service.calendarList().list().execute().get('items', [])
    events = []
    for cal in cals:
        if cal.get('summary') in calendars:
            events_result = service.events().list(calendarId=cal.get('id'), timeMin=now,
                                            timeMax=end, singleEvents=True,
                                            orderBy='startTime').execute()
            events += events_result.get('items', [])
    busy_times = []
    time_buffer = datetime.timedelta(minutes=buf)
    for event in events:
        if 'dateTime' not in event['start']:
            continue
        start = datetime.datetime.fromisoformat(event['start'].get('dateTime')) - time_buffer
        start = start.replace(tzinfo=None)
        end = datetime.datetime.fromisoformat(event['end'].get('dateTime')) + time_buffer
        end = end.replace(tzinfo=None)
        busy_times.append(Time(start, True, True, False))
        busy_times.append(Time(end, False, True, False))
    return busy_times

def free_time(times, min_time=60):
    min_time = datetime.timedelta(minutes=min_time)
    free_times = []
    counter = 0
    prev = None
    is_pot_free = False
    for time in sorted(times, key=lambda x: x.time):
        prev_counter = counter
        if time.busy:
            if time.is_start:
                counter += 1
            else:
                counter -= 1
        if time.pot_free:
            is_pot_free = time.is_start
            if is_pot_free and counter == 0:
                prev = time
            else:
                if prev is not None:
                    if time.time >= prev.time + min_time:
                        free_times.append((prev.time, time.time))
                    prev = None
        if counter != prev_counter and counter * prev_counter == 0 and is_pot_free:
            if prev is not None:
                if time.time >= prev.time + min_time:
                    free_times.append((prev.time, time.time))
                prev = None
            else:
                prev = time
    return free_times

def get_potential_freetimes(days, hours=[(9, 12), (12, 17)], weekends=False):
    freetimes = []
    for start_hour, end_hour in hours:
        start = datetime.datetime.utcnow()
        start = start.replace(hour=start_hour, minute=0, second=0, microsecond=0)

        end = datetime.datetime.utcnow()
        end = end.replace(hour=end_hour, minute=0, second=0, microsecond=0)
            
        day = datetime.timedelta(days=1)
        for i in range(days):
            if not (start + i * day).weekday() in (6, 7) or weekends:
                freetimes.append(Time(start + i * day, True, False, True))
                freetimes.append(Time(end + i * day, False, False, True))
    return freetimes

def free_times_to_hr(times):
    current_date = min(times, key=lambda x: x[0])[0].date()
    free_intervals = []
    for start, end in sorted(times, key=lambda x: x[0]):
        if current_date != start.date():
            print(f"{current_date.strftime('%a %m/%d')}: " + ", ".join(free_intervals))
            free_intervals = []
            current_date = start.date()
        free_intervals.append(f"{start.strftime('%I:%M%p').lstrip('0')}-{end.strftime('%I:%M%p').lstrip('0')}")
    print(f"{current_date.strftime('%a %m/%d')}: " + ", ".join(free_intervals))

def get_parser():
    parser = argparse.ArgumentParser(description="free me from manual scheduling")
    parser.add_argument('--calendars', nargs='+', default=['primary'], help="name of calendars from which events will be drawn")
    parser.add_argument('--free', nargs='+', default=[(9, 12), (13, 17)], help="24hr time tuples that are the boundries for theoretical free time")
    parser.add_argument('--weekends', action="store_true", default=False, help="pass this if you want to schedule things on weekends")
    parser.add_argument('--buffer', type=int, default=10, help="number of minutes to buffer free time from calendar events")
    parser.add_argument('--min-free', type=int, default=60, help="number of minutes that free time must exceed to be reported")
    parser.add_argument('--days', type=int, default=7, help="number of days in the future to report freetime (excludes today)")
    return parser

if __name__ == '__main__':
    parser = get_parser().parse_args()
    pot_free = get_potential_freetimes(parser.days, parser.free, parser.weekends)
    busy_times = get_busy_times(parser.calendars, parser.days, parser.buffer)
    times = free_time(pot_free + busy_times, parser.min_free)
    free_times_to_hr(times)

