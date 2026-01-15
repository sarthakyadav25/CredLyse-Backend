"""
API Dependencies

Reusable dependencies for API routes including authentication.
"""

import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import decode_access_token
from app.models.user import User


# OAuth2 scheme for token extraction from Authorization header
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """
    Dependency to get the current authenticated user.
    
    This dependency:
    1. Extracts the JWT token from the Authorization header
    2. Decodes and validates the token
    3. Fetches the user from the database
    4. Raises 401 if token is invalid or user not found
    
    Args:
        token: JWT token from Authorization header (auto-extracted).
        db: Database session (auto-injected).
        
    Returns:
        User: The authenticated user object.
        
    Raises:
        HTTPException: 401 if authentication fails.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    # Decode the JWT token
    payload = decode_access_token(token)
    if payload is None:
        raise credentials_exception
    
    # Extract user ID from token payload
    user_id_str: str | None = payload.get("sub")
    if user_id_str is None:
        raise credentials_exception
    
    try:
        user_id = uuid.UUID(user_id_str)
    except ValueError:
        raise credentials_exception
    
    # Fetch user from database
    result = await db.execute(
        select(User).where(User.id == user_id)
    )
    user = result.scalar_one_or_none()
    
    if user is None:
        raise credentials_exception
    
    return user


async def get_current_active_user(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    """
    Dependency to get the current active user.
    
    This is a sub-dependency of get_current_user that can be extended
    to check additional conditions (e.g., is_active flag, email verified).
    
    Args:
        current_user: User from get_current_user dependency.
        
    Returns:
        User: The authenticated and active user.
        
    Raises:
        HTTPException: 400 if user is inactive.
    """
    # Add additional checks here if needed (e.g., is_active, is_verified)
    # For now, we just return the user as-is
    return current_user


# Optional OAuth2 scheme that doesn't require authentication
oauth2_scheme_optional = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


async def get_current_user_optional(
    token: Annotated[str | None, Depends(oauth2_scheme_optional)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User | None:
    """
    Dependency to optionally get the current authenticated user.
    
    Similar to get_current_user but returns None instead of raising
    an exception if no valid token is provided.
    
    Args:
        token: Optional JWT token from Authorization header.
        db: Database session (auto-injected).
        
    Returns:
        User | None: The authenticated user or None if not authenticated.
    """
    if not token:
        return None
    
    # Decode the JWT token
    payload = decode_access_token(token)
    if payload is None:
        return None
    
    # Extract user ID from token payload
    user_id_str: str | None = payload.get("sub")
    if user_id_str is None:
        return None
    
    try:
        user_id = uuid.UUID(user_id_str)
    except ValueError:
        return None
    
    # Fetch user from database
    result = await db.execute(
        select(User).where(User.id == user_id)
    )
    user = result.scalar_one_or_none()
    
    return user
