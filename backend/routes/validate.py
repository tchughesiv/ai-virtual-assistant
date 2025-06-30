""" """

import requests
from fastapi import APIRouter
from llama_stack.distribution.server.auth_providers import AuthRequest, AuthResponse

router = APIRouter(prefix="/validate", tags=["validate"])


def make_authorized_request(
    url, token, method="GET", data=None, json=None, headers=None, **kwargs
):
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
        **kwargs: Additional keyword arguments to pass to requests.request().

    Returns:
        requests.Response: The response object from the request.
    """
    if not token.startswith("Bearer "):
        auth_header_value = f"Bearer {token}"
    else:
        auth_header_value = token

    default_headers = {
        "Authorization": auth_header_value,
    }

    if headers:
        default_headers.update(headers)

    try:
        response = requests.request(
            method=method,
            url=url,
            headers=default_headers,
            data=data,
            json=json,
            **kwargs,
        )
        response.raise_for_status()
        return response
    except requests.exceptions.HTTPError as e:
        print(f"HTTP Error: {e}")
        print(f"Response content: {e.response.text}")
        return None
    except requests.exceptions.ConnectionError as e:
        print(f"Connection Error: {e}")
        return None
    except requests.exceptions.Timeout as e:
        print(f"Timeout Error: {e}")
        return None
    except requests.exceptions.RequestException as e:
        print(f"An error occurred: {e}")
        return None


@router.post("", response_model=AuthResponse)
@router.post("/", response_model=AuthResponse)
def validate(auth_request: AuthRequest):
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

    response = make_authorized_request(
        url="http://localhost:8887/validate-token",
        token=auth_request.api_key,
        headers=auth_request.request.headers,
    )
    if response is not None:
        for key, value in response.headers.items():
            print(f"{key}: {value}")
        if response.status_code == 200:
            return AuthResponse(
                principal="test",
                attributes={"test", "test"},
                message="Authentication successful",
            )

    return None
