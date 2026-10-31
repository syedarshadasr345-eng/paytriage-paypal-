from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.database import init_db, get_all_invoices
from backend.seed import seed_database
from backend.recovery.router import router as recovery_router
from backend.recovery.config import SCORING_VERSION
from backend.config import APP_NAME, APP_TAGLINE, APP_PACKAGE_NAME


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize DB schema
    init_db()
    # If database has 0 invoices, seed with initial demo dataset
    invoices = get_all_invoices()
    if not invoices:
        seed_database()
    yield


app = FastAPI(
    title=f"{APP_NAME} — {APP_TAGLINE}",
    description=f"{APP_NAME}: {APP_TAGLINE} Explainable payment recovery intelligence for merchants. Scores overdue invoices, recommends next-best actions, and compares recovery strategies.",
    version=SCORING_VERSION,
    lifespan=lifespan,
)

# CORS Middleware for future frontend integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Routers
app.include_router(recovery_router)


@app.get("/api/health", tags=["health"])
def health_check():
    return {
        "status": "healthy",
        "service": f"{APP_PACKAGE_NAME}-backend",
        "scoring_version": SCORING_VERSION,
    }


@app.get("/", tags=["root"])
def root():
    return {
        "app": f"{APP_NAME} — {APP_TAGLINE}",
        "scoring_version": SCORING_VERSION,
        "docs_url": "/docs",
        "health_check": "/api/health",
        "queue_url": "/api/recovery/queue",
    }
