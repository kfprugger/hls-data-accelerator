from datetime import datetime

from dmf.utils.global_constants import GlobalConstants


def to_timestamp(str_timestamp: str, datetime_format: str = f"{GlobalConstants.DATE_FORMAT} %H:%M:%S"):
    return datetime.strptime(str_timestamp, datetime_format)


def to_date(str_date: str, date_format: str = GlobalConstants.DATE_FORMAT):
    return datetime.strptime(str_date, date_format).date()
