from contextlib import asynccontextmanager

from fastapi import FastAPI

import app.models  # noqa: F401 — registers all models with Base.metadata
from app.database import Base, engine
from app.routers.blocks import router as blocks_router
from app.routers.engine import router as engine_router
from app.routers.slots import router as slots_router
from app.routers.tasks import router as tasks_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: create all tables if they don't already exist
    Base.metadata.create_all(bind=engine)
    yield
    # Shutdown: nothing to clean up for now


app = FastAPI(title="LifeOps API", lifespan=lifespan)

app.include_router(blocks_router, prefix="/api/v1")
app.include_router(tasks_router, prefix="/api/v1")
app.include_router(slots_router, prefix="/api/v1")
app.include_router(engine_router, prefix="/api/v1")


@app.get("/health")
def health():
    return {"status": "ok"}
