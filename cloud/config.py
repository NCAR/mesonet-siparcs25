import os
import yaml
import logging

logger = logging.getLogger(__name__)

def load_config():
    config_file = os.getenv("CONFIG_FILE_PATH", "config.yml")
    if not os.path.isfile(config_file):
        logger.error(f"Config file '{config_file}' not found.")
        raise RuntimeError(f"Config file '{config_file}' not found.")
    
    try:
        with open(config_file, "r") as f:
            config = yaml.safe_load(f)
        logger.debug(f"Config loaded: {config}")
        if not config or 'mqtt' not in config or 'web' not in config:
            logger.error("Invalid configuration or missing required sections (mqtt, web)")
            raise RuntimeError("Invalid configuration")
        return config
    except Exception as e:
        logger.error(f"Error reading config: {e}")
        raise RuntimeError(f"Error reading config: {e}")