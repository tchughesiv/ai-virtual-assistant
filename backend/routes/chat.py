import enum
import json
import os
from typing import AsyncIterator

from fastapi import Request

# from llama_stack_client import AgentEventLogger
from llama_stack_client.lib.agents.react.tool_parser import ReActOutput

from ..agents import ExistingAsyncAgent, ExistingReActAgent
from ..api.llamastack import get_client_from_request
from ..utils.logging_config import get_logger

logger = get_logger(__name__)


class AgentType(enum.Enum):
    REGULAR = "Regular"
    REACT = "ReAct"


class Chat:
    """
    A stateless class for handling chat interactions with LlamaStack.

    This class no longer maintains local state and instead retrieves
    everything from LlamaStack APIs using agent_id and session_id.

    Args:
        logger: Logger object for logging messages.

    Methods:
        stream: Streams the chatbot's response based on agent_id,
                session_id, and prompt.
    """

    def __init__(self, logger, request: Request):
        os.environ["TOKENIZERS_PARALLELISM"] = "false"
        self.log = logger
        self.request = request

    def _get_client(self):
        return get_client_from_request(self.request)

    async def _get_agent_config(self, agent_id: str):
        """
        Retrieve agent configuration from LlamaStack.

        Args:
            agent_id: The unique identifier of the agent

        Returns:
            Agent configuration object or None if not found
        """
        try:
            agent_config = await self._get_client().agents.retrieve(agent_id=agent_id)
            return agent_config
        except Exception as e:
            self.log.error(f"Error retrieving agent config for {agent_id}: {e}")
            return None

    async def _get_tools_for_agent(self, agent_id: str):
        """
        Retrieve tools configuration for an agent from LlamaStack.

        Args:
            agent_id: The unique identifier of the agent

        Returns:
            List of tools available to the agent
        """
        try:
            agent_config = await self._get_agent_config(agent_id)
            if (
                agent_config
                and hasattr(agent_config, "tool_config")
                and agent_config.tool_config
            ):
                return agent_config.tool_config.tools
            return []
        except Exception as e:
            self.log.error(f"Error retrieving tools for agent {agent_id}: {e}")
            return []

    async def _get_model_for_agent(self, agent_id: str):
        """
        Retrieve model configuration for an agent from LlamaStack.

        Args:
            agent_id: The unique identifier of the agent

        Returns:
            Model identifier string, defaults to llama-3.1-8b-instruct if not found
        """
        try:
            agent_config = await self._get_agent_config(agent_id)
            if agent_config and hasattr(agent_config, "model"):
                return agent_config.model
            # Fallback to default model if not found
            models = await self._get_client().models.list()
            model_list = [
                model.identifier for model in models if model.api_model_type == "llm"
            ]
            return model_list[0] if model_list else "llama-3.1-8b-instruct"
        except Exception as e:
            self.log.error(f"Error retrieving model for agent {agent_id}: {e}")
            return "llama-3.1-8b-instruct"

    async def _create_agent_with_existing_id(self, agent_id: str, session_id: str):
        """Create an agent instance using an existing agent_id from LlamaStack."""
        try:
            print(agent_id)
            agent_config = await self._get_agent_config(agent_id)
            if not agent_config:
                raise Exception(f"Agent {agent_id} not found")

            model = await self._get_model_for_agent(agent_id)
            tools = await self._get_tools_for_agent(agent_id)
            print("tools = " + tools)

            # Determine agent type from config (default to REGULAR)
            agent_type = AgentType.REGULAR

            # Create agent instance using existing ID
            if agent_type == AgentType.REACT:
                return ExistingReActAgent(
                    self._get_client(),
                    agent_id=agent_id,
                    model=model,
                    tools=tools,
                    response_format={
                        "type": "json_schema",
                        "json_schema": ReActOutput.model_json_schema(),
                    },
                    sampling_params={"strategy": {"type": "greedy"}, "max_tokens": 512},
                )
            else:
                return ExistingAsyncAgent(
                    self._get_client(),
                    agent_id=agent_id,
                    model=model,
                    instructions=(
                        "You are a helpful assistant. When you use a tool "
                        "always respond with a summary of the result."
                    ),
                    tools=tools,
                    sampling_params={
                        "strategy": {"type": "greedy"},
                        "max_tokens": 512,
                    },
                )  # .initialize()
        except Exception as e:
            self.log.error(f"Error creating agent with ID {agent_id}: {e}")
            raise

    def _response_generator(
        self, turn_response, session_id: str, agent_type: AgentType
    ):
        if agent_type == AgentType.REACT:
            return self._handle_react_response(turn_response, session_id)
        else:
            return self._handle_regular_response(turn_response, session_id)

    def _handle_react_response(self, turn_response, session_id: str):
        current_step_content = ""
        final_answer = None
        tool_results = []

        # Send session ID first to help client initialize the connection
        yield json.dumps({"type": "session", "sessionId": session_id})

        for response in turn_response:
            if not hasattr(response.event, "payload"):
                error_msg = (
                    "\n\n🚨 Llama Stack server Error: "
                    "The response received is missing an expected "
                    "`payload` attribute. This could indicate a malformed "
                    "response or an internal issue within the server.\n\n"
                    f"Error details: {response}"
                )
                yield json.dumps({"type": "error", "content": error_msg})
                return

            payload = response.event.payload

            if payload.event_type == "step_progress" and hasattr(payload.delta, "text"):
                current_step_content += payload.delta.text
                continue

            if payload.event_type == "step_complete":
                step_details = payload.step_details

                if step_details.step_type == "inference":
                    for chunk in self._process_inference_step_json(
                        current_step_content, tool_results, final_answer
                    ):
                        yield chunk
                    current_step_content = ""
                elif step_details.step_type == "tool_execution":
                    tool_results = self._process_tool_execution(
                        step_details, tool_results
                    )
                    current_step_content = ""
                else:
                    current_step_content = ""

        if not final_answer and tool_results:
            for chunk in self._format_tool_results_summary_json(tool_results):
                yield chunk

    def _process_inference_step(self, current_step_content, tool_results, final_answer):
        """Original method for backward compatibility"""
        try:
            react_output_data = json.loads(current_step_content)
            answer = react_output_data.get("answer")

            if answer and answer != "null" and answer is not None:
                final_answer = answer

            if answer and answer != "null" and answer is not None:
                yield f"\n\n✅ **Final Answer:**\n{answer}"

        except json.JSONDecodeError:
            yield (
                f"\n\nFailed to parse ReAct step content:\n"
                f"```json\n{current_step_content}\n```"
            )
        except Exception as e:
            yield (
                f"\n\nFailed to process ReAct step: {e}\n"
                f"```json\n{current_step_content}\n```"
            )

        return final_answer

    def _process_inference_step_json(
        self, current_step_content, tool_results, final_answer
    ):
        """JSON-emitting version for AI SDK compatibility"""
        try:
            react_output_data = json.loads(current_step_content)
            thought = react_output_data.get("thought")
            action = react_output_data.get("action")
            answer = react_output_data.get("answer")

            if answer and answer != "null" and answer is not None:
                final_answer = answer

            # Emit thought as reasoning
            if thought:
                yield json.dumps({"type": "reasoning", "content": thought})

            # Emit action as tool
            if action and isinstance(action, dict):
                tool_name = action.get("tool_name")
                tool_params = action.get("tool_params")
                if tool_name:
                    yield json.dumps(
                        {
                            "type": "tool",
                            "content": f'Using "{tool_name}" tool',
                            "tool": {"name": tool_name, "params": tool_params},
                        }
                    )

            # Emit final answer
            if answer and answer != "null" and answer is not None:
                yield json.dumps({"type": "text", "content": f"Final Answer: {answer}"})

        except json.JSONDecodeError:
            yield json.dumps(
                {
                    "type": "error",
                    "content": (
                        f"Failed to parse ReAct step content: "
                        f"{current_step_content}"
                    ),
                }
            )
        except Exception as e:
            yield json.dumps(
                {
                    "type": "error",
                    "content": (
                        f"Failed to process ReAct step: {e} - "
                        f"{current_step_content}"
                    ),
                }
            )

        return final_answer

    def _format_tool_results_summary(self, tool_results):
        yield "\n\n**Here's what I found:**\n"
        for tool_name, content in tool_results:
            try:
                parsed_content = json.loads(content)

                if tool_name == "web_search" and "top_k" in parsed_content:
                    yield from self._format_web_search_results(parsed_content)
                elif "results" in parsed_content and isinstance(
                    parsed_content["results"], list
                ):
                    yield from self._format_results_list(parsed_content["results"])
                elif isinstance(parsed_content, dict) and len(parsed_content) > 0:
                    yield from self._format_dict_results(parsed_content)
                elif isinstance(parsed_content, list) and len(parsed_content) > 0:
                    yield from self._format_list_results(parsed_content)
            except json.JSONDecodeError:
                yield (
                    f"\n**{tool_name}** was used but returned complex data. "
                    "Check the observation for details.\n"
                )
            except (TypeError, AttributeError, KeyError, IndexError) as e:
                logger.error(
                    f"Error processing {tool_name} result: {type(e).__name__}: {e}"
                )

    def _process_tool_execution(self, step_details, tool_results):
        try:
            if hasattr(step_details, "tool_responses") and step_details.tool_responses:
                for tool_response in step_details.tool_responses:
                    tool_name = tool_response.tool_name
                    content = tool_response.content
                    tool_results.append((tool_name, content))

                    logger.debug("")
                    try:
                        parsed_content = json.loads(content)
                        logger.debug(parsed_content)
                    except json.JSONDecodeError:
                        logger.debug(content)

            else:
                logger.debug("⚙️ Observation")
                logger.debug(
                    "Tool execution step completed, but no response data found."
                )
                pass
        except Exception as e:
            logger.error(f"Error processing tool execution: {str(e)}")

        return tool_results

    def _format_web_search_results(self, parsed_content):
        for i, result in enumerate(parsed_content["top_k"], 1):
            if i <= 3:
                title = result.get("title", "Untitled")
                url = result.get("url", "")
                content_text = result.get("content", "").strip()
                yield f"\n- **{title}**\n  {content_text}\n  [Source]({url})\n"

    def _format_results_list(self, results):
        for i, result in enumerate(results, 1):
            if i <= 3:
                if isinstance(result, dict):
                    name = result.get("name", result.get("title", "Result " + str(i)))
                    description = result.get(
                        "description", result.get("content", result.get("summary", ""))
                    )
                    yield f"\n- **{name}**\n  {description}\n"
                else:
                    yield f"\n- {result}\n"

    def _format_dict_results(self, parsed_content):
        yield "\n```\n"
        for key, value in list(parsed_content.items())[:5]:
            if isinstance(value, str) and len(value) < 100:
                yield f"{key}: {value}\n"
            else:
                yield f"{key}: [Complex data]\n"
        yield "```\n"

    def _format_list_results(self, parsed_content):
        yield "\n"
        for _, item in enumerate(parsed_content[:3], 1):
            if isinstance(item, str):
                yield f"- {item}\n"
            elif isinstance(item, dict) and "text" in item:
                yield f"- {item['text']}\n"
            elif isinstance(item, dict) and len(item) > 0:
                first_value = next(iter(item.values()))
                if isinstance(first_value, str) and len(first_value) < 100:
                    yield f"- {first_value}\n"

    def _format_tool_results_summary_json(self, tool_results):
        """JSON-emitting version of tool results summary for AI SDK compatibility"""
        summary_text = "Here's what I found:\n"

        for tool_name, content in tool_results:
            try:
                parsed_content = json.loads(content)

                if tool_name == "web_search" and "top_k" in parsed_content:
                    # Format web search results
                    for i, result in enumerate(parsed_content["top_k"], 1):
                        if i <= 3:
                            title = result.get("title", "Untitled")
                            url = result.get("url", "")
                            content_text = result.get("content", "").strip()
                            summary_text += (
                                f"\n- **{title}**\n  {content_text}\n  "
                                f"[Source]({url})\n"
                            )

                elif "results" in parsed_content and isinstance(
                    parsed_content["results"], list
                ):
                    # Format results list
                    for i, result in enumerate(parsed_content["results"], 1):
                        if i <= 3:
                            if isinstance(result, dict):
                                name = result.get(
                                    "name", result.get("title", "Result " + str(i))
                                )
                                description = result.get(
                                    "description",
                                    result.get("content", result.get("summary", "")),
                                )
                                summary_text += f"\n- **{name}**\n  {description}\n"
                            else:
                                summary_text += f"\n- {result}\n"

                elif isinstance(parsed_content, dict) and len(parsed_content) > 0:
                    # Format dictionary results
                    summary_text += "\n```\n"
                    for key, value in list(parsed_content.items())[:5]:
                        if isinstance(value, str) and len(value) < 100:
                            summary_text += f"{key}: {value}\n"
                        else:
                            summary_text += f"{key}: [Complex data]\n"
                    summary_text += "```\n"

                elif isinstance(parsed_content, list) and len(parsed_content) > 0:
                    # Format list results
                    summary_text += "\n"
                    for _, item in enumerate(parsed_content[:3], 1):
                        if isinstance(item, str):
                            summary_text += f"- {item}\n"
                        elif isinstance(item, dict) and "text" in item:
                            summary_text += f"- {item['text']}\n"
                        elif isinstance(item, dict) and len(item) > 0:
                            first_value = next(iter(item.values()))
                            if isinstance(first_value, str) and len(first_value) < 100:
                                summary_text += f"- {first_value}\n"

            except json.JSONDecodeError:
                summary_text += (
                    f"\n**{tool_name}** was used but returned complex data.\n"
                )
            except (TypeError, AttributeError, KeyError, IndexError) as e:
                summary_text += (
                    f"\n**{tool_name}** was used but encountered an error: "
                    f"{type(e).__name__}\n"
                )

        # Return as JSON object with type and content
        yield json.dumps({"type": "text", "content": summary_text})

    async def _handle_regular_response(
        self, turn_response: AsyncIterator, session_id: str
    ):
        # Send session ID first to help client initialize the connection
        yield json.dumps({"type": "session", "sessionId": session_id})

        async for response in turn_response:
            print(response)
            if hasattr(response.event, "payload"):
                logger.debug(response.event.payload)
                if response.event.payload.event_type == "step_progress":
                    if hasattr(response.event.payload.delta, "text"):
                        # Format as JSON for AI SDK compatibility
                        yield json.dumps(
                            {
                                "type": "text",
                                "content": response.event.payload.delta.text,
                            }
                        )
                if response.event.payload.event_type == "step_complete":
                    if (
                        response.event.payload.step_details.step_type
                        == "tool_execution"
                    ):
                        if response.event.payload.step_details.tool_calls:
                            tool_call = response.event.payload.step_details.tool_calls[
                                0
                            ]
                            tool_name = str(tool_call.tool_name)
                            yield json.dumps(
                                {
                                    "type": "tool",
                                    "content": f'Using "{tool_name}" tool:',
                                    "tool": {"name": tool_name},
                                }
                            )
                        else:
                            yield json.dumps(
                                {
                                    "type": "text",
                                    "content": "No tool_calls present in step_details",
                                }
                            )
            else:
                yield json.dumps(
                    {
                        "type": "error",
                        "content": (
                            f"Error occurred in the Llama Stack Cluster: " f"{response}"
                        ),
                    }
                )

    async def stream(self, agent_id: str, session_id: str, prompt: str):
        """
        Stream chat response using LlamaStack as the single source of truth.

        Args:
            agent_id: The ID of the agent from LlamaStack
            session_id: The ID of the session from LlamaStack
            prompt: The user's message
        """
        try:
            # Create agent instance using existing agent_id
            agent = await self._create_agent_with_existing_id(agent_id, session_id)

            print(f"Using agent: {agent_id} with session: {session_id}")
            self.log.info(f"Using agent: {agent_id} with session: {session_id}")

            # Get existing messages from the session
            # Note: LlamaStack manages session state, so we don't need to
            # maintain local state
            messages = [{"role": "user", "content": prompt}]

            # Create turn with LlamaStack
            turn_response = await agent.create_turn(
                session_id=session_id,
                messages=messages,
                stream=True,
            )

            # Determine agent type (defaulting to REGULAR for now)
            agent_type = AgentType.REGULAR
            print(turn_response)
            print(agent.tools)
            print(agent.agent_id)
            print(prompt)

            # async for event in AgentEventLogger().log(turn_response):
            #    event.print()

            # Stream the response
            self._response_generator(turn_response, session_id, agent_type)

        except Exception as e:
            self.log.error(
                f"Error in stream for agent {agent_id}, session {session_id}: {e}"
            )
            yield json.dumps(
                {
                    "type": "error",
                    "content": (
                        f"Error occurred while processing your request: {str(e)}"
                    ),
                }
            )
