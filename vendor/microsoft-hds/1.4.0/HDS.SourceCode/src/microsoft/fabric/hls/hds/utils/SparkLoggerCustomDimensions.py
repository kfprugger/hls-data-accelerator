import logging

class CustomDimensionsFilter(logging.Filter):
    """
    Add properties to AzureLogHandler records
    """
    
    def __init__(self, custom_dimensions=None):
        super().__init__()
        self.custom_dimensions = custom_dimensions or {}

    def filter(self, record):
        """
        Adds the default custom_dimensions into the current log record
        """
        
        cdim = self.custom_dimensions.copy()
        cdim.update({
            "LogLevel": record.levelname,
            "LoggerName": record.name,
            "FunctionName": record.funcName,
            "LineNumber": record.lineno,
        })
        cdim.update(getattr(record, 'custom_dimensions', {}))
        record.custom_dimensions = cdim
        return True