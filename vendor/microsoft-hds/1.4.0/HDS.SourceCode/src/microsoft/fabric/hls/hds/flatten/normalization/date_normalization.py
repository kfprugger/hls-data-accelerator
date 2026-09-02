# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# --------------------------------------------------------------------------
from typing import Union
import datetime
import re
from microsoft.fabric.hls.hds.flatten.constants import FlattenConstants as C

class DateNormalization:
    @staticmethod
    def normalize_date(date: Union[str, datetime.datetime, datetime.date, None])\
            -> Union[datetime.datetime,None]:
        """
        Normalization of the data string

        Following the logic from https://github.com/hlstests/a3/blob/master/algorithm.md
        """
        generated_str = None
        if date is None:
            return None
        # return date types without normalization
        if isinstance(date, datetime.datetime):
            return date
        # add zero time to the date without normalization
        if isinstance(date, datetime.date):
            return datetime.datetime.combine(date, datetime.datetime.min.time()).\
                replace(tzinfo=datetime.timezone.utc)
        # we dont support other types rather string and datetime
        if not isinstance(date, str):
            return None
        # try to match the string
        if re.match(pattern=C.RE_DATE_YEAR, string=date):
            generated_str = f"{date}-01-01 00:00:00.000+0000"
        if re.match(pattern=C.RE_DATE_YEAR_MONTH, string=date):
            generated_str = f"{date}-01 00:00:00.000+0000"
        if re.match(pattern=C.RE_DATE_YEAR_MONTH_DAY, string=date):
            generated_str = f"{date} 00:00:00.000+0000"
        if re.match(pattern=C.RE_DATE_TIME_PART, string=date):
            parts = re.match(
                pattern=C.RE_DATE_FULL_PARTS, string=date)
            if parts:
                # get 3 numbers milliseconds part with leading .
                mil_seconds_parts = '.000'
                if parts[4]:
                    mil_seconds_parts = str(
                        parts[4] or '')+'.000'[len(str(parts[4] or '')):]

                timezone_part = "+0000"
                # if timezone already present in +00 or -00 format, leave as is
                if parts[5] and (parts[5][0] == '+' or parts[5][0] == '-'):
                    timezone_part = parts[5].replace(":", "")
                generated_str = f"{parts[1]} {parts[3]}{mil_seconds_parts}{timezone_part}"
        if generated_str:
            return datetime.datetime.strptime(generated_str, '%Y-%m-%d %H:%M:%S.%f%z')
        return None