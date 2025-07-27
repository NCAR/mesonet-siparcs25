import json
import requests
from datetime import datetime, timezone
from typing import List
from utils import CustomLogger, request

class LLMModel:
    def __init__(self, logger: CustomLogger, model_names: List[str], model_service_base_url: str):
        self.console = logger
        self.model_names = model_names
        self.model_service_base_url = model_service_base_url

        self.test_api_connection()

    def __get_current_timestamp(self):
        return datetime.now(timezone.utc).isoformat()

    async def __query_model_service(self, station_id: str, sensor_data: dict, forecast_data, model_name: str) -> dict:
        """
        Query the LLM model service with the given sensor data and return the summary.
        """
        console = self.console

        payload = {
            "data": json.dumps(sensor_data),
            "forecast_data": json.dumps(forecast_data),
            "model": model_name
        }

        try:
            url = f"{self.model_service_base_url}/predict"
            response = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=200)
            if response.status_code == 200:
                console.log(f"[info]: Successfully queried {model_name} for station {station_id}")
                return response.json().get("result", "")
            else:
                console.error(f"[error]: Failed to query {model_name} for station {station_id}: {response.text}")
                return ""
        except requests.RequestException as e:
            console.error(f"[error]: Failed to communicate with model_service for {model_name}: {e}")
            return ""
    
    def test_api_connection(self):
        res = request.ping(f"{self.model_service_base_url}/health")

        if res.status_code == 200:  
            self.console.log(f"LLM Model Service is reachable at {self.model_service_base_url}.")
        else:
            self.console.error("LLM Model Service is not reachable. Please check the configuration.")
            raise ConnectionError("LLM Model Service connection failed.")
        
    async def run(self, station_id: str, data: dict, forecast_data: dict) -> dict:
        model_summaries = {}
        if not data:
            self.console.warning("No data provided for model query.")
            return model_summaries
        
        for model_name in self.model_names:
            summary = await self.__query_model_service(station_id, {
                **data, **forecast_data,
                "timestamp": self.__get_current_timestamp()
                },
                model_name
            )
            if summary:
                model_summaries[model_name] = summary

        return model_summaries
