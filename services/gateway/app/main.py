import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers.system import router as system_router
from app.routers.ingestion import router as ingestion_router
from app.services.health_poller import poll_loop

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("Gateway starting. Launching health poller.")
    poller = asyncio.create_task(poll_loop())
    yield
    poller.cancel()
    log.info("Gateway shutdown.")


app = FastAPI(
    title="Perception Platform — Gateway",
    version="0.1.0",
    description="BFF gateway. Single point of communication between the UI and all pipeline modules.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tightened via env in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(system_router)
app.include_router(ingestion_router)
