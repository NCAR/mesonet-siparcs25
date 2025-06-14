from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from database import Database
from crud import ReadWriteDB
from logger import CustomLogger

app = FastAPI("IoTwx APIs")
console = CustomLogger() 
db = Database()
db.base.metadata.create_all(bind=db.engine)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Replace "*" with specific origins in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def root():
    return {"message": "API is reachable"}

@app.get("/stations")
def read_stations(db: Session = Depends(db.get_db)):
    service = ReadWriteDB(db)
    return service.get_stations()

@app.get("/stations/{station_id}")
def read_station(station_id: str, db: Session = Depends(db.get_db)):
    service = ReadWriteDB(db)
    station = service.get_station(station_id)
    if not station:
        raise HTTPException(status_code=404, detail="Station not found")
    return station

@app.post("/stations")
def create_station(data: dict, db: Session = Depends(db.get_db)):
    service = ReadWriteDB(db)
    return service.create_station(data)

@app.put("/stations/{station_id}")
def update_station(station_id: str, data: dict, db: Session = Depends(db.get_db)):
    service = ReadWriteDB(db)
    updated = service.update_station(station_id, data)
    if not updated:
        raise HTTPException(status_code=404, detail="Station not found")
    return updated
