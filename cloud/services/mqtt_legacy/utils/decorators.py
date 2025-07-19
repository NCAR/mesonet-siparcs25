import functools
from logger import CustomLogger

def premium(reason: str = "premium feature", logger: CustomLogger = CustomLogger(name="mqtt_logs", log_dir="/cloud/logs")):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            logger.warning(f"⚠️ {func.__name__} is disabled: {reason}")
            # Optionally, raise an exception or return a placeholder
            return None
        return wrapper
    return decorator