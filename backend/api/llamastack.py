import os
from typing import Optional

from dotenv import load_dotenv
from fastapi import Request
from llama_stack_client import LlamaStackClient

from ..virtual_agents.agent_resource import EnhancedAgentResource

load_dotenv()

LLAMASTACK_URL = os.getenv("LLAMASTACK_URL", "http://localhost:8321")


def get_sa_token():
    file_path = "/var/run/secrets/kubernetes.io/serviceaccount/token"
    try:
        with open(file_path, "r") as file:
            token = file.read()
            return token
    except FileNotFoundError:
        print(f"Error: The file '{file_path}' was not found.")
    except Exception as e:
        print(f"An error occurred: {e}")


def get_client(
    api_key: Optional[str], headers: Optional[dict[str, str]]
) -> LlamaStackClient:
    client = LlamaStackClient(
        base_url=LLAMASTACK_URL,
        default_headers=headers,
    )
    if api_key:
        client.api_key = api_key
    client.agents = EnhancedAgentResource(client)
    return client


def get_client_from_request(request: Optional[Request]) -> LlamaStackClient:
    token = get_sa_token()
    headers = token_to_auth_header(token)
    user_headers = get_user_headers_from_request(request)
    headers.update(user_headers)

    return get_client(token, headers)


def token_to_auth_header(token: str) -> dict[str, str]:
    if not token.startswith("Bearer "):
        auth_header_value = f"Bearer {token}"
    else:
        auth_header_value = token

    return {"Authorization": auth_header_value}


def get_user_headers_from_request(request: Optional[Request]) -> dict[str, str]:
    headers = {}
    if request is not None:
        user_header = request.headers.get("X-Forwarded-User")
        if not user_header:
            user_header = request.headers.get("x-forwarded-user")
        if user_header:
            headers["X-Forwarded-User"] = user_header

        email_header = request.headers.get("X-Forwarded-Email")
        if not email_header:
            email_header = request.headers.get("x-forwarded-email")
        if email_header:
            headers["X-Forwarded-Email"] = email_header

    return headers


def get_sync_client() -> LlamaStackClient:
    token = get_sa_token()
    headers = token_to_auth_header(token)
    headers["X-Forwarded-User"] = os.getenv("ADMIN_USERNAME")
    return get_client(token, headers)


sync_client = get_sync_client()
