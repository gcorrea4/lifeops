from contextlib import asynccontextmanager

from fastapi import FastAPI

import app.models  # noqa: F401 — registers all models with Base.metadata
from app.database import Base, engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: create all tables if they don't already exist
    Base.metadata.create_all(bind=engine)
    yield
    # Shutdown: nothing to clean up for now


app = FastAPI(title="LifeOps API", lifespan=lifespan)


@app.get("/health")
def health():
    return {"status": "ok"}
