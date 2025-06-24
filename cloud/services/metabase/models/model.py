from utils.session import Session
from logger import CustomLogger
from utils.odm import ODM

class Model(ODM):
    def __init__(self, session: Session, logger: CustomLogger):
        super().__init__(session)
        self.console = logger
        self.console.debug("Initializing Model for dynamic SQL queries")
        self.path = "dataset"

    def get_measurements(self, query: str, db_id: int, collection_id="root"):
        """
        Returns a list of measurements.
        """
        payload = {
            "database": db_id,
            "type": "native",
            "native": {
                "query": query
            },
            "collection_id": collection_id
        }
        measurements = self.add_one(self.path, payload)
        return [measurement[0] for measurement in measurements["data"]["rows"]]
    
    def build_measurement_query(self, station_id: str) -> str:
        """
        Builds a query to retrieve unique measurements for a given station.
        """
        return f"""
            SELECT DISTINCT measurement
            FROM readings
            WHERE station_id = '{station_id}' AND reading_value != 0
            ORDER BY measurement;
        """

    # --- Build the SQL Model Dynamically ---
    def build_pivot_query(self, measurements: list, station_id: str, timezone: str="America/Denver") -> str:
        pivot_columns = ",\n\t\t".join([
            f"COALESCE(ROUND(AVG(CASE WHEN measurement = '{m}' THEN reading_value END)::numeric, 2), 0) AS \"{m.lower()}\""
            for m in measurements
        ])

        measurement_columns = ",\n\t\t".join([
            f"r_pivot.\"{m.lower()}\"" for m in measurements
        ])

        model_query = f"""
            SELECT
                s.station_id,
                r_pivot.rounded_time AT TIME ZONE 'UTC' AT TIME ZONE '{timezone}' AS timestamp,
                {measurement_columns}
            FROM stations s
            JOIN (
                SELECT
                    station_id,
                    DATE_TRUNC('minute', timestamp) AS rounded_time,
                    {pivot_columns}
                FROM readings
                WHERE station_id = '{station_id}'
                GROUP BY station_id, rounded_time
            ) r_pivot ON s.station_id = r_pivot.station_id
            WHERE s.station_id = '{station_id}'
            ORDER BY r_pivot.rounded_time DESC;
        """

        return model_query.strip()


