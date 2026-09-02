import logging
from logging import getLevelName

class ContextLoggerAdapter(logging.LoggerAdapter):
    
    def process(self, msg, kwargs):
        log_level = getLevelName(self.logger.getEffectiveLevel())
        index = self.extra['index']
        config_name = self.extra['config_name']
        task_index = self.extra['task_index']

        formatted_log = f"[Pipeline {index}: {config_name}] [Task {task_index}] [{log_level}] {msg}"
        return formatted_log, kwargs