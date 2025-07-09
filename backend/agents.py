from typing import Any, Callable, List, Optional, Tuple, Union

from llama_stack_client.lib.agents.agent import AgentConfig, AsyncAgent
from llama_stack_client.lib.agents.client_tool import ClientTool
from llama_stack_client.lib.agents.react.agent import ReActAgent
from llama_stack_client.lib.agents.tool_parser import ToolParser
from llama_stack_client.types import SamplingParams
from llama_stack_client.types.agents.turn_create_params import Toolgroup
from llama_stack_client.types.shared_params.agent_config import ToolConfig


class ExistingAgent(AsyncAgent):
    """An extension of the Agent class with an existing agent_id."""

    def __init__(
        self,
        client,
        agent_id: str,
        model: Optional[str] = None,
        instructions: Optional[str] = None,
        tools: Optional[List[Union[Toolgroup, ClientTool, Callable[..., Any]]]] = None,
        tool_config: Optional[ToolConfig] = None,
        sampling_params: Optional[SamplingParams] = None,
        max_infer_iters: Optional[int] = None,
        agent_config: Optional[AgentConfig] = None,
        client_tools: Tuple[ClientTool, ...] = (),
        tool_parser: Optional[ToolParser] = None,
    ):
        # Call parent's __init__ but skip the initialize() call
        self.client = client
        self.model = model
        self.instructions = instructions
        self.tools = tools or []
        self.tool_config = tool_config
        self.sampling_params = sampling_params
        self.max_infer_iters = max_infer_iters
        self.agent_config = agent_config
        self.client_tools = client_tools
        self.tool_parser = tool_parser
        self.sessions = []
        self.builtin_tools = {}

        # Set the agent_id directly instead of calling initialize()
        # self.agent_id = agent_id


class ExistingReActAgent(ReActAgent):
    """An extension of the ReActAgent class with an existing agent_id."""

    def __init__(
        self,
        client,
        agent_id: str,
        model: Optional[str] = None,
        tools: Optional[List[Union[Toolgroup, ClientTool, Callable[..., Any]]]] = None,
        tool_config: Optional[ToolConfig] = None,
        sampling_params: Optional[SamplingParams] = None,
        max_infer_iters: Optional[int] = None,
        response_format: Optional[dict] = None,
        agent_config: Optional[AgentConfig] = None,
        client_tools: Tuple[ClientTool, ...] = (),
        tool_parser: Optional[ToolParser] = None,
    ):
        # Call parent's __init__ but skip the initialize() call
        self.client = client
        self.model = model
        self.tools = tools or []
        self.tool_config = tool_config
        self.sampling_params = sampling_params
        self.max_infer_iters = max_infer_iters
        self.response_format = response_format
        self.agent_config = agent_config
        self.client_tools = client_tools
        self.tool_parser = tool_parser
        self.sessions = []
        self.builtin_tools = {}

        # Set the agent_id directly instead of calling initialize()
        self.agent_id = agent_id
