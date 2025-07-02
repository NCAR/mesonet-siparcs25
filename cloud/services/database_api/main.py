from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from database.connection import Base, async_engine
from routes import station, reading, user
from logger import CustomLogger

app = FastAPI(
    title="IoTwx",
    description="APIs for accessing IoTwx databases",
    version="0.0.1",
    docs_url="/api/docs"
)
console = CustomLogger(name="database_logs", log_dir="/cloud/logs")

async def init_db():
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Replace "*" with specific origins in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def on_startup():
    await init_db()

@app.get("/health")
def health():
    console.log("Health check pinged.")
    return {"status": "ok"}

app.include_router(station.router)
app.include_router(reading.router)
app.include_router(user.router)
