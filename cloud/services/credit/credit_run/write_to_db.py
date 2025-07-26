import asyncio
import pandas as pd
import numpy as np
from rpds import List
from traitlets import Any
from logger import CustomLogger
from utils import request, Payload
from utils.type_c import CreditCreate, CreditUpdate, CreditResponse

console = CustomLogger(name="credit_logs", log_dir="/cloud/logs")
file_path = "results/2025-07-25T00Z_Forecast/Data/forecast_000.xlsx"

class CreditToDB:
    def __init__(self):
        self.db_uri = ""
        self.__db_url = ""
        console.log(f"The file to read data from: {file_path}")

    @property
    def db_url(self):
        return self.__db_url
    
    @db_url.setter
    def db_url(self, value: str):
        if value:
            self.__db_url = value
            self.db_uri = f"{value}/api/credit-forecast"

    def connect_to_db(self, path: str = None):
        """
        Connect to the database using the provided URI.
        """
        path = path if path else self.db_url
        console.log(f"Testing database connection {path}")
        res = request.ping(f"{path}/health")
        console.log(f"Database connection status: {res.get('status')}")

    async def get_stations(self) -> List:
        """
        Fetch the list of stations from the database.
        """
        url = f"{self.db_url}/api/stations/"
        stations = await request.get_all(url)

        if not stations:
            return []
        
        return stations
    
    def interpolate_station_location(self, station_lat, station_lon, df: pd.DataFrame) -> pd.DataFrame:
        """
        Interpolate the nearest station location using Euclidean distance between all points and the station.
        """
        console.log(f"Calculate the nearest prediction for the station at ({station_lat, station_lon})")
        df["euc_dist"] = np.sqrt((df["latitude"] - station_lat)**2 + (df["longitude"] - station_lon)**2)
        nearest_station = df.loc[df["euc_dist"].idxmin()]
        console.debug(f"""Nearest station:\n{nearest_station}""")

        return nearest_station

    async def __write_data(self):
        """
        Write the provided excel data to the database.
        """
        df = pd.read_excel(file_path)

        if df.empty:
            console.error("Excel file is empty. No data to write to the database.")
            return
        
        console.log("Fetching stations from the database...")
        stations = await self.get_stations()
        console.log(f"Found {len(stations)} stations in the database.")

        if not stations:
            console.error("No stations found in the database. Credit need current stations to map predictions to.")
            return
        
        for station in stations:
            station_id = station.get("station_id")
            station_lon = station.get("longitude")
            station_lat = station.get("latitude")

            if not (station_id and station_lon and station_lat):
                console.error("Station ID and location is missing in the station data. These are required to map predictions to the station.")
                continue
            
            console.log(f"Processing data for station: {station_id}")
            station_data = self.interpolate_station_location(station_lat, station_lon, df)

            if station_data.empty:
                console.warning(f"No data found for station {station_id}. Skipping...")
                continue

            station_data = station_data.to_dict()

            payload = Payload() \
                .reset() \
                .set_attr("station_id", station_id) \
                .set_attr("longitude", station_data.get("longitude")) \
                .set_attr("latitude", station_data.get("latitude")) \
                .set_attr("forecast_for", station_data.get("time").isoformat()) \
                .set_attr("temperature", station_data.get("t2m")) \
                .build()

            res = await request.insert(path=self.db_uri, data=payload)

            console.debug(f"Credit forecast post response: {res}")

    async def run(self):
        """
        Main method to execute the credit run and write results to the database.
        """
        try:
            # Write data to the database
            await self.__write_data()

            console.log("Data written to the database successfully.")
        except Exception as e:
            console.error(f"An error occurred: {e}")

if __name__ == "__main__":
    async def main():
        try:
            app = CreditToDB()

            try:
                db_url = "http://database-api:8000"
                app.connect_to_db(db_url)
            except:
                db_url = "http://database_api:8000"
                app.connect_to_db(db_url)
            finally:
                app.db_url = db_url

            await app.run()
        except Exception as e:
            console.exception(f"General error occurred: {e}")

    asyncio.run(main())
