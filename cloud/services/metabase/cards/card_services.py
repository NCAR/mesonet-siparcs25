from utils.session import Session
from logger import CustomLogger
from .card import Card

class CardServices:
    def __init__(self, session: Session, logger: CustomLogger, db_id: str):
        self.console = logger
        self.card = Card(session, logger)
        self.db_id = db_id
        self.__card_id = None

    @property
    def id(self) -> str:
        return self.__card_id

    def __create_card(self, name: str, display: str, question: object, collection_id: str = "root", visualization: dict = {}) -> str:
        self.card.name = name
        self.console.log(f"Creating card: {self.card.name}")
        card_id = self.card.create(question, display, vis_settings=visualization, collection_id=collection_id)
        self.__card_id = card_id

    def create_map_card(self, station_id: str, collection_id: str = "root") -> None:
        map_query = f"SELECT * FROM stations LIMIT 10"
        question = {
            "type": "native",
            "native": {"query": map_query},
            "database": self.db_id
        }
        visualization = {
            "map.latitude_column": "latitude",
            "map.longitude_column": "longitude",
            "color_enabled": False,
            "size_enabled": False,
            "map.type": "pin"
        }
        name = f"{station_id}'s Map"
        display = "map"
        self.__create_card(name, display, question, collection_id, visualization)

    def create_table_card(self, model_name: str, model_query: str, station_id: str, collection_id: str = "root") -> None:
        self.card.name = model_name
        question = {
            "type": "native",
            "native": {"query": model_query},
            "database": self.db_id
        }
        self.console.log(f"Creating model card: {self.card.name} for station: {station_id}")
        self.card.create(question=question, display="table", collection_id=collection_id)