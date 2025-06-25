from logger import CustomLogger
from utils.odm import ODM
from utils.session import Session

class Dashboard(ODM):
    def __init__(self, session: Session, logger: CustomLogger, name: str = None):
        super().__init__(session)
        self.console = logger
        self.__name = name if name else "IoTwx Dashboard"
        self.__path = "dashboard"
        self.console.debug(f"Dashboard initialized with name: {self.__name}")
    
    def __get_dashboard(self, id):
        return self.get_one(self.__path, id)
    
    def __update_dashboard(self, id, payload):
        dash = self.update_one(self.__path, id, payload)
        dash_id = dash.get("id")
        if dash_id:
            self.console.log(f"Dasboard: {dash_id}/{self.__name} is updated successfully")

    def __add_dashboard(self, payload):
        dash = self.add_one(self.__path, payload)
        dash_id = dash.get("id")
        if dash_id:
            self.console.log(f"Dashboard: {dash_id}/{self.__name} is added successfully")
            return dash_id
        
    @property
    def name(self) -> str:
        return self.__name
    
    @name.setter
    def name(self, value: str):
        if value:
            self.console.debug(f"Setting dashboard name to: {value}")
            self.__name = value
        else:
            self.console.error("Dashboard name cannot be empty.")
            raise ValueError("Dashboard name cannot be empty.")
        
    def create(self, collection_id="root") -> str:
        payload = {"name": self.__name, "collection_id": collection_id}
        dashboards = self.get_all(self.__path)
        dash_id = self._exists(dashboards, self.__name)
        if dash_id is None:
            return self.__add_dashboard(payload)
        
        return dash_id
    
    def add_card(self, dash_id, card_id) -> None:
        payload = self.__get_dashboard(dash_id)
        dashcards = payload.get("dashcards", [])
        new_card = {
            "id": dash_id,
            "card_id": card_id,
            "col": 1,
            "row": len(dashcards),
            "size_x": 30,
            "size_y": 10
        }

        if len(dashcards) != 0:
            dashcards_cp = dashcards
            for dashcard in dashcards:
                if dashcard.get("card_id") != card_id:
                    dashcards_cp.append(new_card)
                    payload["dashcards"] = dashcards_cp
                    break
        else:
            dashcards.append(new_card)
            payload["dashcards"] = dashcards

        # console.debug(f"Updated dashboard payload:\n%s {json.dumps(payload, indent=4)}")
        self.__update_dashboard(dash_id, payload)
