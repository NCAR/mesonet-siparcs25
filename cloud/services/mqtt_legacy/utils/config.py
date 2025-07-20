import os
import yaml
from dotenv import load_dotenv
from string import Template

class Config:
    def __init__(self, filepath="/cloud/config.yaml", required_fields=None):
        load_dotenv()
        default_required_fields = {
            "mqtt": ["host", "host2", "port", "msg_topic", "topics"],
            "database_api": ["base_url"],
            "map": ["host", "port"],
            "redis": ["host", "port"],
            "station": ["active_station_timeout", "batch_interval"],
            "model_service": ["base_url", "model_name"],
            "metabase": [
                "admin_data", "config", "settings", "database", "base_url", "orch_url"
            ],
            "thingsboard": [
                "broker_ip", "broker_port", "api_url", "username", "password",
                "default_device_type", "dashboard_name"
            ],
        }

        required_fields = {**default_required_fields, **(required_fields or {})}

        with open(filepath, "r") as f:
            content = Template(f.read()).substitute(os.environ)

        if not content.strip():
            raise ValueError("Configuration file is empty or not properly formatted.")

        self.__data = yaml.safe_load(content)

        self.__validate_required_fields(required_fields)

    def __validate_required_fields(self, required_fields):
        for section, fields in required_fields.items():
            if section not in self.__data:
                raise ValueError(f"Missing section '{section}' in configuration.")
            for field in fields:
                if field not in self.__data[section]:
                    raise ValueError(f"Missing field '{field}' in section '{section}' of configuration.")

    @property
    def metabase(self):
        return self.__data["metabase"]
    
    @property
    def database_api(self):
        return self.__data["database_api"]
    
    @property
    def mqtt(self):
        return self.__data["mqtt"]
    
    @property
    def redis(self):
        return self.__data["redis"]
    
    @property
    def station(self):
        return self.__data["station"]
