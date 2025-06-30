import os
from typing import Optional

from dotenv import load_dotenv
from fastapi import Request
from llama_stack_client import LlamaStackClient

from ..virtual_agents.agent_resource import EnhancedAgentResource

load_dotenv()

LLAMASTACK_URL = os.getenv("LLAMASTACK_URL", "http://localhost:8321")


def get_token_from_authorization_header(authorization_header: str):
    """
    Extracts the token from an Authorization header string.

    Args:
        authorization_header (str): The full value of the Authorization header,
                                    e.g., "Bearer your_access_token".

    Returns:
        str or None: The extracted token string, or None if the header is invalid.
    """
    if not authorization_header:
        return None

    parts = authorization_header.split()
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1]
    elif len(parts) == 2 and parts[0].lower() == "token":  # For 'Token {token}' scheme
        return parts[1]
    else:
        return None


def get_client(api_key: Optional[str]) -> LlamaStackClient:
    client = LlamaStackClient(
        base_url=LLAMASTACK_URL,
    )
    if api_key is not None:
        client.api_key = api_key
    client.agents = EnhancedAgentResource(client)
    return client


def get_client_from_request(request: Optional[Request]) -> LlamaStackClient:
    if request is not None:
        for key, value in request.headers.items():
            print(f"{key}: {value}")
        return get_client(
            get_token_from_authorization_header(request.headers.get("Authorization"))
        )
    return get_client()


sync_client = get_client(os.getenv("TOKEN"))
