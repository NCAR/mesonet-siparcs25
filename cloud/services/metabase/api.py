from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from apis.users import routes as users
from apis.emails import routes as emails
from apis.groups import routes as groups

app = FastAPI(
    title="IoTwx Metabase APIs",
    description="APIs for accessing IoTwx metabase APIs",
    version="0.0.1",
    docs_url="/metabase/docs"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Replace "*" with specific origins in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
def health():
    print("Health check pinged.")
    return {"status": "ok"}

app.include_router(users.router)
app.include_router(emails.router)
app.include_router(groups.router)
