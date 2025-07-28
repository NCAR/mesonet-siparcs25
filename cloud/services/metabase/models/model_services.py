from utils.session import Session
from logger import CustomLogger
from .model import Model
from cards.card_services import CardServices

class ModelServices:
    def __init__(self, session: Session, logger: CustomLogger, db_id: int):
        self.console = logger
        self.model = Model(session, logger)
        self.card = CardServices(session, logger, db_id)
        self.db_id = db_id

    def create_station_pivot(self, station_id: str, collection_id: str = "root") -> None:
        measurement_query = self.model.build_measurement_query(station_id)
        measurement = self.model.get_measurements(measurement_query, self.db_id, collection_id)
        # console.debug(f"Fetched measurements: {measurement}")
        model_query = self.model.build_pivot_query(measurement, station_id)
        model_name = f"{station_id}'s Readings"

        if len(measurement) and model_query:
            self.card.create_table_card(
                model_name=model_name,
                model_query=model_query,
                station_id=station_id,
                collection_id=collection_id
            )
            self.console.log(f"Pivot model card created for station: {station_id} with name: {model_name}")
