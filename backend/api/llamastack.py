import os

from dotenv import load_dotenv
from llama_stack_client import LlamaStackClient

from ..virtual_agents.agent_resource import EnhancedAgentResource

load_dotenv()

LLAMASTACK_URL = os.getenv("LLAMASTACK_URL", "http://localhost:8321")

def get_client(api_key: str | None) -> LlamaStackClient:
    client = LlamaStackClient(
        base_url=LLAMASTACK_URL,
    )
    if api_key is not None:
        client.api_key = api_key
    client.agents = EnhancedAgentResource(client)
    return client

sync_client = get_client(os.getenv("TOKEN"))
