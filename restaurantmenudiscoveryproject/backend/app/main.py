from fastapi import FastAPI

from app.db import init_db
from app.routers import restaurants

app = FastAPI(title="Restaurant Menu Discovery API")
app.include_router(restaurants.router)


@app.on_event("startup")
def on_startup() -> None:
    init_db()


@app.get("/health")
def health():
    return {"status": "ok"}
