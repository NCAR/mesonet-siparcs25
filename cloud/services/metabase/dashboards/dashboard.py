from logger import CustomLogger
from utils.odm import Util

console = CustomLogger()

class Dashboard(Util):
    def __init__(self, session, name):
        super().__init__(session)
        self.name = name
        self.path = "dashboard"
    
    def __get_dashboard(self, id):
        return self.get_one(self.path, id)
    
    def __update_dashboard(self, id, payload):
        dash = self.update_one(self.path, id, payload)
        dash_id = dash.get("id")
        if dash_id:
            console.log(f"Dasboard: {dash_id}/{self.name} is updated successfully")

    def __add_dashboard(self, payload):
        dash = self.add_one(self.path, payload)
        dash_id = dash.get("id")
        if dash_id:
            console.log(f"Dashboard: {dash_id}/{self.name} is added successfully")
            return dash_id

    def create(self):
        payload = {"name": self.name}
        dashboards = self.get_all(self.path)
        dash_id = self._exists(dashboards, self.name)
        if dash_id is None:
            return self.__add_dashboard(payload)
        
        return dash_id
    
    def add_card(self, dash_id, card_id):
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
