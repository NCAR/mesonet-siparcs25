from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from database.connection import Base, engine
from routes import station
from logger import CustomLogger

app = FastAPI(title="IoTwx APIs")
console = CustomLogger() 
Base.metadata.create_all(bind=engine)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Replace "*" with specific origins in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(station.router)

@app.get("/health")
def health():
    console.log("Health check pinged.")
    return {"status": "ok"}
