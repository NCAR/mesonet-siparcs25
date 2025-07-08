from utils.payload import Payload
from utils.session import Session
from utils.odm import ODM
from logger import CustomLogger

class Collection(ODM):
    def __init__(self, session: Session, logger: CustomLogger, name: str = None, description: str = None):
        super().__init__(session)
        self.console = logger
        self.__name = name if name else "IoTwx Collection"
        self.__description = description if description else "Collection for IoTwx related dashboards and cards"
        self.__path = "collection"
        self.console.debug(f"Collection initialized with name: {self.__name}")

    @property
    def name(self) -> str:
        return self.__name
    
    @name.setter
    def name(self, value: str) -> None:
        if value:
            self.console.debug(f"Setting collection name to: {value}")
            self.__name = value
        else:
            self.console.error("Collection name cannot be empty.")
            raise ValueError("Collection name cannot be empty.")
        
    @property
    def description(self) -> str:
        return self.__description
    
    @description.setter
    def description(self, value: str) -> None:
        if value:
            self.console.debug(f"Setting collection description to: {value}")
            self.__description = value
        else:
            self.console.error("Collection description cannot be empty.")
            raise ValueError("Collection description cannot be empty.")

    def create(self, parent_id = None) -> str:
        payload = Payload() \
            .set_attr("name", self.__name) \
            .set_attr("description", self.__description) \
            .set_attr("parent_id", parent_id) \
            .build()
        
        collections = self.get_all(self.__path)
        collection_id = self._exists(collections, self.__name)
        if collection_id is None:
            collection = self.add_one(self.__path, payload)
            collection_id = collection.get("id")
            if collection_id:
                self.console.log(f"Collection: {self.__name} is added successfully with ID: {collection_id}")
                return collection_id
            else:
                self.console.error(f"Failed to create collection: {self.__name}")
                return "root"  # Default to root if creation fails
        else:
            self.console.log(f"Collection: {self.__name} already exists with ID: {collection_id}")
            return collection_id
