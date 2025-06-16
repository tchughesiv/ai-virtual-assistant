"""
Profile API endpoint(s) ??? for authentication and user administration ??.

????? This module provides CRUD operations for user accounts, including user creation,
authentication, role management, and profile updates. It handles password hashing
and role-based access control for the AI Virtual Assistant application.

Key Features:
- Check user authentication
- Return user profile
"""

from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from pydantic import BaseModel
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from .. import models, schemas
from ..database import get_db

router = APIRouter(prefix="/profile", tags=["profile"])

# Dummy secret and algorithm
SECRET_KEY = "your_secret_key"
ALGORITHM = "HS256"


# Define the OAuth2 scheme
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


class TokenData(BaseModel):
    username: Optional[str] = None


async def get_user(username: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(models.User).where(models.User.username == username))
    user = result.scalar_one_or_none()
    if user:
        return user
    return None


async def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
        token_data = TokenData(username=username)
    except JWTError:
        raise credentials_exception

    user = get_user(username=token_data.username)
    if user is None:
        raise credentials_exception
    return user


@router.get("/", response_model=schemas.UserRead)
async def read_profile(current_user: models.User = Depends(get_current_user)):
    return current_user
