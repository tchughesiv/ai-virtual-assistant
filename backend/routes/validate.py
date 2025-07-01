""" """

import httpx
from fastapi import APIRouter, HTTPException, status
from llama_stack.distribution.server.auth_providers import AuthRequest, AuthResponse

router = APIRouter(prefix="/validate", tags=["validate"])


async def make_authorized_request(
    url: str,
    token: str,
    headers=dict[str, str],
) -> httpx.Response | None:
    """
    Makes an HTTP request with an Authorization header.

    Args:
        url (str): The URL to make the request to.
        token (str): The authorization token (e.g., JWT, API key).
                     This will be prefixed with 'Bearer ' if not already.
        method (str): The HTTP method (e.g., 'GET', 'POST', 'PUT', 'DELETE').
                      Defaults to 'GET'.
        data (dict or str): Data to send in the request body for POST/PUT.
        json (dict): JSON data to send in the request body for POST/PUT.
        headers (dict): Optional dictionary of additional headers.

    Returns:
        requests.Response: The response object from the request.
    """
    default_headers = token_to_auth_header(token)
    headers.update(default_headers)

    for key, value in headers.items():
        print(f"{key}: {value}")

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
async def validate(auth_request: AuthRequest):
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
        url="http://localhost:8887/validate-token",
        token=auth_request.api_key,
        headers=auth_request.request.headers,
    )

    if response is None or response.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Authentication failed: {response.status_code}",
        )

    return AuthResponse(principal="test", message="Authentication successful")


def token_to_auth_header(token: str) -> dict[str, str]:
    if not token.startswith("Bearer "):
        auth_header_value = f"Bearer {token}"
    else:
        auth_header_value = token

    return {"Authorization": auth_header_value}
