import asyncio
import json
import redis
from datetime import datetime, timezone, timedelta
from typing import Any, Dict
from redis_c import RedisClient
from utils import CustomLogger, request
from llm_model import LLMModel
from collections import defaultdict

class Batch:
    def __init__(
        self,
        logger: CustomLogger,
        model: LLMModel,
        redis_client: RedisClient,
        db_url: str,
        batch_interval=60,\
    ):
        self.console = logger
        self.redis_client = redis_client
        self.batch_interval = batch_interval
        self.model = model
        self.db_url = db_url

        self.buffer_lock = asyncio.Lock()
        self.sensor_buffer = {}
        self.last_processed = {}

        asyncio.create_task(self.process_batch_loop())

    @property
    def readings_buffer(self):
        return self.sensor_buffer

    async def set_readings_buffer(self, readings: Dict[str, Any]):
        measurement = readings.get("measurement", "")
        reading_value = str(readings.get("reading_value", ""))
        sensor = readings.get("sensor_model", "unknown")
        target_id = readings.get('target_id', "")
        rssi = readings.get('rssi')
        station_id = readings.get("station_id")
        timestamp = readings.get("timestamp", datetime.now(timezone.utc).isoformat())

        if not station_id:
            self.console.error("Station ID is required for writing batch data.")
            return

        ts_raw = readings.get('timestamp', timestamp)
        ts_iso = (
            datetime.fromtimestamp(ts_raw, tz=timezone.utc).isoformat()
            if isinstance(ts_raw, (int, float))
            else ts_raw.isoformat()
        )

        async with self.buffer_lock:
            station = self.sensor_buffer.setdefault(station_id, {"data": {}, "metadata": {}})
            station_data: dict = station["data"]
            station_meta: dict = station["metadata"]

            if measurement not in ['latitude', 'longitude', 'altitude']:
                sensor_entry = station_data.setdefault(sensor, {})
                sensor_entry[measurement] = reading_value
            else:
                station_meta[measurement] = reading_value

            # Always update last_active and optional metadata
            station_meta["last_active"] = ts_iso
            if target_id:
                station_meta["target_id"] = target_id
            if rssi:
                station_meta["rssi"] = str(rssi)
            

    def __merge_sensor_data(self, existing_data: Dict[str, Any], new_data: Dict[str, Any]) -> Dict[str, Any]:
        merged = existing_data.copy()
        merged.setdefault("data", {})
        for sensor, measurements in new_data.get("data", {}).items():
            merged["data"].setdefault(sensor, {}).update(measurements)
        return merged

    def __merge_metadata(self, existing_metadata: Dict[str, Any], new_metadata: Dict[str, Any]) -> Dict[str, Any]:
        return {**existing_metadata, **new_metadata}

    async def process_batch_loop(self):
        while True:
            await asyncio.sleep(self.batch_interval)
            if self.sensor_buffer:
                await self.process_batch()

    async def process_batch(self):
        console = self.console

        async with self.buffer_lock:
            batch_data = self.sensor_buffer.copy()
        inactive_stations = []
        current_time = datetime.now(timezone.utc)
        for station_id, readings in batch_data.items():
            if not station_id or not readings:
                console.warning(f"Invalid station reading for ID: {station_id}")
                continue

            last_active = readings.get("metadata", {}).get("last_active")   
            if last_active:
                try:
                    last_active = datetime.fromisoformat(last_active)
                    time_diff = (current_time - last_active).total_seconds()
                    if time_diff > self.active_station_timeout:
                        inactive_stations.append(station_id)
                        print(f"[info]: Station {station_id} inactive for {time_diff}s, marking as inactive")
                    
                except ValueError:
                    print(f"[warn]: Invalid last_active timestamp for station {station_id}: {last_active}")

            if self.last_processed.get(station_id) == last_active:
                console.debug(f"Skipping reprocessing for {station_id} (unchanged timestamp)")
                continue

            self.last_processed[station_id] = last_active
            if station_id in inactive_stations:
                readings["metadata"]["active"] = False
            else:
                readings["metadata"]["active"] = True

            try:
                redis_key = f"station:{station_id}"

                new_sensor_data = {"data": readings.get("data", {})}
                existing_redis_data = await self.redis_client.hget(redis_key, "data") or "{}"
                existing_sensor_data = json.loads(existing_redis_data)

                new_metadata = {**readings.get("metadata", {}), "last_active": last_active}
                   
                existing_redis_metadata = await self.redis_client.hget(redis_key, "metadata") or "{}"
                existing_metadata = json.loads(existing_redis_metadata)

                merged_sensor_data = self.__merge_sensor_data(existing_sensor_data, new_sensor_data)
                merged_metadata = self.__merge_metadata(existing_metadata, new_metadata)

                model_summaries = await self.model.run(station_id, merged_sensor_data) or []

                all_forecasts = await request.get_all(path=f"{self.db_url}/api/credit-forecast/{station_id}")

                today = datetime.utcnow().date()
                tomorrow = today + timedelta(days=1)

                # --- Group forecasts by station_id and forecast date ---
                tomorrow_forecasts = []

                for forecast in all_forecasts:
                    # Parse the forecast timestamp (assumes ISO format)
                    forecast_dt = datetime.fromisoformat(forecast['forecast_for']).date()
                    if forecast_dt == tomorrow:
                        station_id = forecast['station_id']
                        tomorrow_forecasts[station_id].append({
                            'forecast_for': forecast['forecast_for'],
                            'temperature': forecast['temperature'],
                            'humidity': forecast['humidity'],
                            'pressure': forecast['pressure'],
                            'wind_speed': forecast['wind_speed'],
                            'wind_direction': forecast['wind_direction']
                        })
                model_summaries = await self.model.run(station_id, merged_sensor_data, tomorrow_forecasts) or []

                redis_station_data = {
                    "data": json.dumps(merged_sensor_data),
                    "metadata": json.dumps(merged_metadata),
                    "model_summaries": json.dumps(model_summaries),
                    "credit_forecast": json.dumps(tomorrow_forecasts[station_id])
                }

                await self.redis_client.hset(redis_key, mapping=redis_station_data)
                console.log(f"Updated Redis reading for station {station_id}")

                # Clean up from memory to avoid growth
                async with self.buffer_lock:
                    self.sensor_buffer.pop(station_id, None)

            except (redis.RedisError, json.JSONDecodeError) as e:
                console.error(f"[error]: Failed to update Redis for station {station_id}: {e}")
