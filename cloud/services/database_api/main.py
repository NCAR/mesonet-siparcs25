from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from database.connection import Base, engine
from routes import station, reading
from logger import CustomLogger

app = FastAPI(
    title="IoTwx",
    description="APIs for accessing IoTwx databases",
    version="0.0.1",
    docs_url="/api/docs"
)
console = CustomLogger(name="database_logs", log_dir="/cloud/logs")
Base.metadata.create_all(bind=engine)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Replace "*" with specific origins in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
def health():
    console.log("Health check pinged.")
    return {"status": "ok"}

app.include_router(station.router)
app.include_router(reading.router)
