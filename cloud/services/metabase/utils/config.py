import os
import yaml
from dotenv import load_dotenv
from string import Template

class Config:
    def __init__(self, filepath="/cloud/config.yaml"):
        load_dotenv()

        with open(filepath, "r") as f:
            content = Template(f.read()).substitute(os.environ)

        if not content.strip():
            raise ValueError("Configuration file is empty or not properly formatted.")
        
        self.__data = yaml.safe_load(content)

    @property
    def metabase(self):
        return self.__data["metabase"]
    
    @property
    def database_api(self):
        return self.__data["database_api"]
