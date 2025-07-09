""" """

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from llama_stack.distribution.server.auth_providers import (
    AuthRequest,
    AuthRequestContext,
    AuthResponse,
    User,
)
from sqlalchemy.ext.asyncio import AsyncSession

from ..api.llamastack import (
    get_sa_token,
    get_user_headers_from_request,
    token_to_auth_header,
)
from ..database import get_db
from ..routes.users import get_user_from_headers

router = APIRouter(prefix="/validate", tags=["validate"])


async def make_authorized_request(
    url: str,
    auth_request: AuthRequest,
) -> httpx.Response | None:
    headers = token_to_auth_header(auth_request.api_key)
    user_headers = get_user_headers_from_request(auth_request.request)
    headers.update(user_headers)

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                url=url,
                headers=headers,
                timeout=10.0,  # Add a reasonable timeout
            )
            return response
    except httpx.TimeoutException:
        raise
    except ValueError:
        raise
    except Exception as e:
        raise ValueError("Authentication service error") from e


@router.post("", response_model=AuthResponse)
@router.post("/", response_model=AuthResponse)
async def validate(auth_request: AuthRequest, db: AsyncSession = Depends(get_db)):
    """
    Validate a bearer token.

    This endpoint fetches an authorized user's profile information.

    Args:
        auth_request: HTTP request details
        db: Database session dependency

    Returns:
        schemas.UserRead: The authorized user's profile

    Raises:
        HTTPException: 401 if the user is not authorized
        HTTPException: 403 if the user is not found
    """

    response = await make_authorized_request(
        "http://localhost:8887/validate-token",
        auth_request,
    )

    if response is None or response.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Authentication failed: {response.status_code}",
        )

    user = await get_user_from_headers(auth_request.request.headers, db)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="User not found"
        )
    return AuthResponse(
        principal=user.username,
        attributes={
            "roles": [user.role],
        },
        message="Authentication successful",
    )


# mimic llama-stack authentication request
@router.post("/test", response_model=User)
async def validate_test(request: Request) -> User:
    # Build the auth request model
    auth_request = AuthRequest(
        api_key=get_sa_token(),
        request=AuthRequestContext(
            path="/",
            headers={
                "x-forwarded-user": request.headers.get("X-Forwarded-User"),
                "x-forwarded-email": request.headers.get("X-Forwarded-Email"),
            },
            params={},
        ),
    )

    # Validate with authentication endpoint
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "http://localhost:8887/validate",
                json=auth_request.model_dump(),
                timeout=10.0,  # Add a reasonable timeout
            )
            if response.status_code != 200:
                print(f"Authentication failed with status code: {response.status_code}")
                raise ValueError(f"Authentication failed: {response.status_code}")

            # Parse and validate the auth response
            try:
                response_data = response.json()
                auth_response = AuthResponse(**response_data)
                return User(auth_response.principal, auth_response.attributes)
            except Exception as e:
                print("Error parsing authentication response")
                raise ValueError("Invalid authentication response format") from e

    except httpx.TimeoutException:
        print("Authentication request timed out")
        raise
    except ValueError:
        # Re-raise ValueError exceptions to preserve their message
        raise
    except Exception as e:
        print("Error during authentication")
        raise ValueError("Authentication service error") from e
