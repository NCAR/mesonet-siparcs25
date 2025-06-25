from utils.session import Session
from logger import CustomLogger
from .dashboard import Dashboard

class DashboardServices:
    def __init__(self, session: Session, logger: CustomLogger, db_id: int):
        self.console = logger
        self.dashboard = Dashboard(session, logger)
        self.__dash_id = None
        self.db_id = db_id

    @property
    def id(self) -> str:
        return self.__dash_id

    def create_dashboard(self, station_id: str, collection_id: str = "root") -> None:
        self.dashboard.name = f"{station_id}'s Dashboard"
        self.console.log(f"Creating dashboard: {self.dashboard.name}")
        self.dash_id = self.dashboard.create(collection_id)
    
    def merge_card(self, card_id: str, alt_dash_id: str = None) -> None:
        dash_id = alt_dash_id if alt_dash_id else self.dash_id
        self.console.log(f"Adding card: {card_id} to dashboard: {dash_id}")
        self.dashboard.add_card(dash_id, card_id)
        self.console.log(f"Card {card_id} added to dashboard {dash_id} successfully.")
