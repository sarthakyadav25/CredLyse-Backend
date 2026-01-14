"""
API v1 Router

Aggregates all v1 endpoint routers.
"""

from fastapi import APIRouter

from app.api.v1.endpoints import auth, users, courses, analysis

router = APIRouter()

# Include authentication routes
router.include_router(auth.router)

# Include user routes
router.include_router(users.router)

# Include course routes
router.include_router(courses.router)

# Include analysis routes
router.include_router(analysis.router)
