import os
from typing import Optional

from dotenv import load_dotenv
from fastapi import Request
from llama_stack_client import LlamaStackClient

from ..virtual_agents.agent_resource import EnhancedAgentResource

load_dotenv()

LLAMASTACK_URL = os.getenv("LLAMASTACK_URL", "http://localhost:8321")


def get_client(api_key: Optional[str]) -> LlamaStackClient:
    client = LlamaStackClient(
        base_url=LLAMASTACK_URL,
    )
    if api_key is not None:
        client.api_key = api_key
    client.agents = EnhancedAgentResource(client)
    return client


def get_client_from_request(request: Optional[Request]) -> LlamaStackClient:
    return get_client(request.headers.get("X-Forwarded-Access-Token"))


sync_client = get_client(os.getenv("TOKEN"))
