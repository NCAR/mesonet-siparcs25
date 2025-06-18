from logger import CustomLogger
from util import Util
import json

console = CustomLogger()

class Card(Util):
    def __init__(self, session, name, question):
        super().__init__(session)
        self.name = name
        self.question = question
        self.path = "card"

    def __add_card(self, payload):
        card = self.add_one(self.path, payload)
        card_id = card.get("id")
        if card_id:
            # console.log(f"Card: {self.name} is added successfully")
            return card_id

    def create(self, display="table", vis_settings={}):
        payload = {
            "name": self.name,
            "dataset_query": self.question,
            "display": display,
            "visualization_settings": vis_settings
        }
        cards = self.get_all(self.path)
        card_id = self._exists(cards, self.name)
        if card_id is None:
            console.debug(f"New card payload:\n%s {json.dumps(payload, indent=4)}")
            return self.__add_card(payload)
        
        return card_id
