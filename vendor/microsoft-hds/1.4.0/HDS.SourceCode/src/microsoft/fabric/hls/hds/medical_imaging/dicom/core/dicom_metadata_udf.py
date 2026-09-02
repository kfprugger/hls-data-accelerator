import json
from datetime import datetime, timezone
from pyspark.sql.functions import udf


def extract_alphabetic(value):
    """
    Extracts the 'Alphabetic' key's value from a dictionary if the input is a dictionary.
    If the input is a string that can be parsed as a JSON dictionary, it attempts to parse it
    and then extract the 'Alphabetic' value. Otherwise, returns the value as is.    
    """
    try:
        if isinstance(value, dict):
            return value.get("Alphabetic")
        elif isinstance(value, str):            
            # Try to parse as JSON if it's a string that looks like a dict
            parsed_value = json.loads(value)            
            return parsed_value.get("Alphabetic")
        else:
            return value  # If it's not a dict or string, return the original value
    except Exception as e:
        return value  # Return original if not a dict or parsable JSON dict

# Define the Python functions
def transform_to_date(arg: str) -> str:
    """
    Transforms a date string from YYYYMMDD to YYYY-MM-DD format.
    Handles None or empty strings gracefully.
    """
    try:
        if arg is None or arg == "":
            return arg
        # Attempt to parse the date string in YYYYMMDD format
        return datetime.strptime(arg, "%Y%m%d").strftime("%Y-%m-%d")
    except Exception as e:
        # In case of an error (e.g., malformed date string), return the original argument
        # print(f"Error transforming date '{arg}': {e}") # Uncomment for debugging
        return arg

def transform_to_time(arg: str) -> str:
    try:
        if arg is None or arg == "":
            return arg            
        time_split = arg.split(".")
        time_split[0] = ':'.join(time_split[0][i:i + 2] for i in range(0, len(time_split[0]), 2)) 
        return ".".join(time_split)            
    except Exception as e:
        return arg