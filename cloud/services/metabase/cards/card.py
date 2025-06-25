from logger import CustomLogger
from utils.odm import ODM
from utils.session import Session

class Card(ODM):
    def __init__(self, session: Session, logger: CustomLogger, name: str = None):
        super().__init__(session)
        self.console = logger
        self.__name = name if name else "IoTwx Card"
        self.__path = "card"
        self.console.debug(f"Card initialized with name: {self.__name}")

    def __add_card(self, payload):
        card = self.add_one(self.__path, payload)
        card_id = card.get("id")
        if card_id:
            self.console.log(f"New Card: {self.__name} is added successfully")
            return card_id
        
    @property
    def name(self):
        return self.__name
    
    @name.setter
    def name(self, value: str):
        self.__name = value
        self.console.log(f"Card name updated to: {self.__name}")

    def create(self, question: object, display="table", vis_settings={}, collection_id="root"):
        payload = {
            "name": self.__name,
            "dataset_query": question,
            "display": display,
            "visualization_settings": vis_settings,
            "collection_id": collection_id,
            "is_model": True
        }
        cards = self.get_all(self.__path)
        card_id = self._exists(cards, self.__name)
        if card_id is None:
            # console.debug(f"New card payload:\n%s {json.dumps(payload, indent=4)}")
            return self.__add_card(payload)
        
        return card_id
