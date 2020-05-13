import datetime
import pytz


def utc_timestamp_to_utc_datetime_string(x):
    return datetime.datetime.utcfromtimestamp(x).strftime('%Y-%m-%d %H:%M:%S')


def timestampz_to_string(x):
    localtz = pytz.timezone('UTC')
    y = x.astimezone(localtz)
    # return y.strftime("%d-%b-%Y %H:%M:%S")
    return y.strftime("%d-%b-%Y")


def get_date_range_in_utc_str(client_timezone_str):
    client_timezone = pytz.timezone(client_timezone_str)
    utc_timezone = pytz.timezone("UTC")
    time_range = list()
    client_datetime_now = datetime.datetime.now(client_timezone)
    numdays = 6
    for i in range(numdays + 1):
        date = client_datetime_now - datetime.timedelta(days=numdays - i)
        client_date = date.strftime('%b %d')
        start_date = date.replace(hour=0, minute=0, second=0, microsecond=0)
        start_date = start_date.astimezone(utc_timezone)
        start_date_utc_str = start_date.strftime('%Y-%m-%d %H:%M:%S')
        end_date = client_datetime_now
        if i != numdays:
            end_date = date.replace(hour=23, minute=59, second=59, microsecond=999999)
        end_date = end_date.astimezone(utc_timezone)
        end_date_utc_str = end_date.strftime('%Y-%m-%d %H:%M:%S')
        time_range.append((start_date_utc_str, end_date_utc_str, client_date))
    return time_range
