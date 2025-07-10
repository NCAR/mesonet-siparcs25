from typing import List
from apis.collections.schema import CollectionRes
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
        
    async def create_async(self, payload: dict, path: str = None) -> CollectionRes:
        console = self.console
        path = path or self.__path
        name = payload.get("name")

        collections_res = await self.get_all_async(path)
        collections: List[CollectionRes] = collections_res.get("data") or []
        existing_collection = next((c for c in collections if c.get("name") == name), None)

        if existing_collection:
            console.log(f"Collection: '{name}' with ID: '{existing_collection.get('id')}' already exists.")
            return existing_collection
        
        collection_res = await self.add_one_async(path, payload)
        collection: CollectionRes = collection_res.get("data") or {}

        if not collection:
            return {}

        console.log(f"Collection: {name} is added successfully with ID: {collection.get('id')}")
        return collection
