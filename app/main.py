"""
Credlyse Backend - FastAPI Application

Main entry point for the application.
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.database import close_db
from app.api.v1 import router as api_v1_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Application lifespan manager.
    
    Handles startup and shutdown events.
    """
    # Startup
    print("🚀 Starting Credlyse Backend...")
    yield
    # Shutdown
    print("🛑 Shutting down Credlyse Backend...")
    await close_db()


# Create FastAPI application
app = FastAPI(
    title="Credlyse Backend",
    description="Educational platform backend with course management, video tracking, and certificates.",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# Configure CORS
origins = settings.cors_origins_list
# Always allow YouTube for the extension
if "https://www.youtube.com" not in origins:
    origins.append("https://www.youtube.com")

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def add_private_network_access_header(request, call_next):
    response = await call_next(request)
    response.headers["Access-Control-Allow-Private-Network"] = "true"
    return response

# Mount static directory
from fastapi.staticfiles import StaticFiles
import os

os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

# Include API routers
app.include_router(api_v1_router, prefix="/api/v1")


@app.get("/health", tags=["Health"])
async def health_check() -> dict:
    """
    Health check endpoint.
    
    Returns:
        dict: Health status and environment info.
    """
    return {
        "status": "healthy",
        "environment": settings.ENVIRONMENT,
        "version": "0.1.0",
    }


@app.get("/", tags=["Root"])
async def root() -> dict:
    """
    Root endpoint.
    
    Returns:
        dict: Welcome message and API documentation links.
    """
    return {
        "message": "Welcome to Credlyse Backend API",
        "docs": "/docs",
        "health": "/health",
    }
