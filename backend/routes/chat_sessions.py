"""
Chat Sessions API endpoints for managing LlamaStack conversation sessions.

This module provides endpoints for creating, retrieving, and managing chat sessions
that are stored and managed by LlamaStack. Sessions track conversation state,
message history, and agent context for continuous conversations.

Key Features:
- Create new chat sessions with specific agents
- Retrieve session lists filtered by agent
- Get detailed session information including message history
- Delete chat sessions
- Automatic session metadata extraction from LlamaStack

All session data is managed by LlamaStack's session API, providing persistent
conversation state across multiple interactions.
"""

import logging
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Request
from llama_stack_client.types.agents.session import Session
from pydantic import BaseModel

from ..api.llamastack import get_client_from_request
from ..virtual_agents.agent_resource import EnhancedAgentResource
from ..virtual_agents.session_resource import EnhancedSessionResource

log = logging.getLogger(__name__)
router = APIRouter(prefix="/chat_sessions", tags=["chat_sessions"])


class CreateSessionRequest(BaseModel):
    """
    Request model for creating new chat sessions.

    Attributes:
        agent_id: The unique identifier of the agent to create a session for
        session_name: Optional custom name for the session. If not provided,
                     a unique name will be generated automatically
    """

    agent_id: str
    session_name: Optional[str] = None


@router.get("/")
async def get_chat_sessions(
    agent_id: str, request: Request, limit: int = 50
) -> List[dict]:
    """
    Get a list of chat sessions for a specific agent from LlamaStack.

    Retrieves session metadata including session IDs, titles, agent information,
    and timestamps. Sessions are sorted by creation date (newest first) and
    limited to the specified number of results.

    Args:
        agent_id: The unique identifier of the agent to retrieve sessions for
        limit: Maximum number of sessions to return (default: 50)

    Returns:
        List of session summary dictionaries containing:
        - id: Session identifier
        - title: Session display title
        - agent_name: Display name of the associated agent
        - created_at: Session creation timestamp
        - updated_at: Session last update timestamp

    Raises:
        HTTPException: If session retrieval fails or agent is not found
    """
    try:
        log.info(f"Attempting to list sessions for agent {agent_id}")

        # Get the enhanced session resource
        client = get_client_from_request(request)
        session_resource: EnhancedSessionResource = client.agents.session

        # Call the enhanced list method - this now returns List[dict]
        # instead of List[Session]
        sessions_data: List[dict] = await session_resource.list(agent_id=agent_id)

        log.info(f"Successfully retrieved {len(sessions_data)} sessions")

        # Get agent info
        agent_name = "Unknown Agent"
        try:
            agentResource: EnhancedAgentResource = client.agents
            agent = await agentResource.retrieve(agent_id=agent_id)
            agent_name = get_agent_display_name(agent)
        except Exception as e:
            log.warning(f"Could not get agent info: {e}")

        # Convert to response format - now working with dicts instead of Session objects
        sessions_response = [
            {
                "id": session.get("session_id"),  # Use .get() instead of .session_id
                "title": session.get("session_name")
                or f"Chat {session.get('session_id', '')[:8]}...",
                "agent_name": agent_name,
                "created_at": session.get(
                    "started_at"
                ),  # Use .get() instead of .started_at
                "updated_at": session.get(
                    "started_at"
                ),  # Use .get() instead of .started_at
            }
            for session in sessions_data[
                :limit
            ]  # Change variable name from sessions to sessions_data
        ]

        # Sort by created_at descending (newest first) to ensure consistent ordering
        sessions_response.sort(key=lambda x: x.get("created_at") or "", reverse=True)

        return sessions_response

    except Exception as e:
        log.error(f"Error fetching chat sessions: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Failed to fetch chat sessions: {str(e)}"
        )


def get_agent_display_name(agent) -> str:
    """
    Extract a display-friendly name from a LlamaStack agent object.

    This helper function attempts to extract a meaningful display name from
    various agent object formats returned by LlamaStack, with fallback options.

    Args:
        agent: LlamaStack agent object with varying structure

    Returns:
        str: A display-friendly agent name, defaults to "Unknown Agent" if no name found
    """
    if hasattr(agent, "agent_config") and isinstance(agent.agent_config, dict):
        return agent.agent_config.get("name", "Unknown Agent")
    elif hasattr(agent, "name"):
        return agent.name
    elif hasattr(agent, "instructions"):
        instructions = str(agent.instructions)
        return (instructions[:50] + "...") if len(instructions) > 50 else instructions
    return "Unknown Agent"


@router.get("/{session_id}")
async def get_chat_session(session_id: str, agent_id: str, request: Request) -> dict:
    """
    Get detailed information for a specific chat session including message history.

    Retrieves the complete session data from LlamaStack including all conversation
    turns (user messages and assistant responses). If session retrieval fails,
    returns a basic session structure with empty message history.

    Args:
        session_id: The unique identifier of the session to retrieve
        agent_id: The unique identifier of the agent that owns the session

    Returns:
        Dictionary containing complete session details:
        - id: Session identifier
        - title: Session display title
        - agent_name: Display name of the associated agent
        - agent_id: Agent identifier
        - messages: List of conversation messages with role and content
        - created_at: Session creation timestamp
        - updated_at: Session last update timestamp

    Raises:
        HTTPException: If agent is not found (404) or retrieval fails (500)
    """
    try:
        log.info(f"Fetching session {session_id} for agent {agent_id}")

        # Verify agent exists
        client = get_client_from_request(request)
        try:
            agentResource: EnhancedAgentResource = client.agents
            agent = await agentResource.retrieve(agent_id=agent_id)
        except Exception as e:
            log.error(f"Agent {agent_id} not found: {str(e)}")
            raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")

        # Get session history from LlamaStack
        try:
            session_resource: EnhancedSessionResource = client.agents.session
            session: Session = await session_resource.retrieve(
                agent_id=agent_id, session_id=session_id
            )
            log.info(f"Successfully retrieved session: {session_id}")

            # Get turns for the session
            turns = session.turns

            # Convert turns to messages format
            messages = []
            for turn in turns:
                # Add user message
                if hasattr(turn, "input_messages"):
                    for msg in turn.input_messages:
                        if hasattr(msg, "content"):
                            messages.append({"role": "user", "content": msg.content})

                # Add assistant response
                if hasattr(turn, "output_message") and hasattr(
                    turn.output_message, "content"
                ):
                    messages.append(
                        {"role": "assistant", "content": turn.output_message.content}
                    )

            # Get agent name
            agent_name = "Unknown Agent"
            try:
                if hasattr(agent, "agent_config") and isinstance(
                    agent.agent_config, dict
                ):
                    agent_name = agent.agent_config.get("name", agent_name)
                elif hasattr(agent, "instructions"):
                    # Use first few words of instructions as name
                    instructions = (
                        str(agent.instructions)[:50] + "..."
                        if len(str(agent.instructions)) > 50
                        else str(agent.instructions)
                    )
                    agent_name = instructions or agent_name
            except Exception as e:
                log.warning(f"Could not get agent name: {e}")

            return {
                "id": session_id,
                "title": f"Chat {session_id[:8]}...",  # Generate title
                "agent_name": agent_name,
                "agent_id": agent_id,
                "messages": messages,
                # LlamaStack doesn't provide timestamps
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
            }

        except Exception as e:
            log.error(f"Error getting session history: {str(e)}")
            # Return empty session if history fetch fails
            return {
                "id": session_id,
                "title": f"Chat {session_id[:8]}...",
                "agent_name": "Unknown Agent",
                "agent_id": agent_id,
                "messages": [],
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
            }

    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Error fetching chat session: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Failed to fetch chat session: {str(e)}"
        )


@router.delete("/{session_id}")
async def delete_chat_session(session_id: str, agent_id: str, request: Request) -> dict:
    """
    Delete a chat session from LlamaStack.

    Permanently removes the specified chat session and all associated conversation
    history from LlamaStack. This operation cannot be undone.

    Args:
        session_id: The unique identifier of the session to delete
        agent_id: The unique identifier of the agent that owns the session

    Returns:
        Dictionary containing the result of the delete operation from LlamaStack

    Raises:
        HTTPException: If agent is not found (404) or deletion fails (500)
    """
    try:
        # Verify agent exists
        client = get_client_from_request(request)
        try:
            agent = await client.agents.retrieve(agent_id=agent_id)
            log.info(f"Found agent: {agent.agent_id}")
        except Exception as e:
            log.error(f"Agent {agent_id} not found: {str(e)}")
            raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")

        # Delete session from LlamaStack using enhanced session resource
        try:
            session_resource: EnhancedSessionResource = client.agents.session
            result = await session_resource.delete(
                session_id=session_id, agent_id=agent_id
            )
            log.info(f"Successfully deleted session {session_id} for agent {agent_id}")
            return result
        except HTTPException:
            # Re-raise HTTPExceptions from the enhanced resource
            raise
        except Exception as e:
            log.error(f"Error deleting session from LlamaStack: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to delete session from LlamaStack: {str(e)}",
            )

    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Error deleting chat session: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Failed to delete chat session: {str(e)}"
        )


@router.post("/")
async def create_chat_session(
    sessionRequest: CreateSessionRequest, request: Request
) -> dict:
    """
    Create a new chat session for an agent using LlamaStack.

    Creates a new conversation session associated with a specific agent. If no
    session name is provided, generates a unique name with timestamp and random
    component. The session is immediately available for chat interactions.

    Args:
        request: CreateSessionRequest containing:
            - agent_id: The unique identifier of the agent
            - session_name: Optional custom name for the session

    Returns:
        Dictionary containing the created session details:
        - id: Generated session identifier
        - title: Session name/title
        - agent_name: Display name of the associated agent
        - agent_id: Agent identifier
        - messages: Empty list (new session)
        - created_at: Session creation timestamp
        - updated_at: Session creation timestamp

    Raises:
        HTTPException: If agent is not found (404) or session creation fails (500)
    """
    try:
        # Verify agent exists in LlamaStack
        client = get_client_from_request(request)
        try:
            agent = await client.agents.retrieve(agent_id=sessionRequest.agent_id)
            log.info(f"Found agent: {agent.agent_id}")
        except Exception as e:
            log.error(
                f"Agent {sessionRequest.agent_id} not found in LlamaStack: {str(e)}"
            )
            raise HTTPException(
                status_code=404, detail=f"Agent {sessionRequest.agent_id} not found"
            )

        # Generate unique session name
        if sessionRequest.session_name:
            session_name = sessionRequest.session_name
        else:
            # Generate unique name with timestamp and random component
            import random
            import string

            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            random_suffix = "".join(
                random.choices(string.ascii_lowercase + string.digits, k=4)
            )
            session_name = f"Chat-{timestamp}-{random_suffix}"
        try:
            session = await client.agents.session.create(
                agent_id=sessionRequest.agent_id, session_name=session_name
            )
            session_id = session.session_id
            log.info(f"Created LlamaStack session: {session_id}")
        except Exception as e:
            log.error(f"Failed to create session in LlamaStack: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to create session in LlamaStack: {str(e)}",
            )

        # Get agent name for display
        agent_name = "Unknown Agent"
        try:
            if hasattr(agent, "agent_config") and isinstance(agent.agent_config, dict):
                agent_name = agent.agent_config.get("name", agent_name)
            elif hasattr(agent, "name"):
                agent_name = agent.name
            elif hasattr(agent, "instructions"):
                # Use first few words of instructions as name
                instructions = (
                    str(agent.instructions)[:50] + "..."
                    if len(str(agent.instructions)) > 50
                    else str(agent.instructions)
                )
                agent_name = instructions or agent_name
        except Exception as e:
            log.warning(f"Could not get agent name: {e}")

        return {
            "id": session_id,
            "title": session_name,
            "agent_name": agent_name,
            "agent_id": sessionRequest.agent_id,
            "messages": [],
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        }

    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Error creating chat session: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Failed to create chat session: {str(e)}"
        )


@router.get("/debug/{agent_id}")
async def debug_session_listing(agent_id: str, request: Request):
    """
    Debug endpoint for troubleshooting session listing functionality.

    This development/debugging endpoint provides detailed information about
    session listing operations, including agent verification, session resource
    inspection, and method execution results. Used for diagnosing issues
    with LlamaStack session API interactions.

    Args:
        agent_id: The unique identifier of the agent to debug

    Returns:
        Dictionary containing debug information:
        - agent_id: The agent being debugged
        - response_type: Type of response from LlamaStack
        - response_value: Raw response value
        - sessions_count: Number of sessions found
        - sessions: List of session data
        - error: Error message if operation fails

    Note:
        This endpoint should only be used for development and debugging purposes.
    """
    try:
        log.info(f"=== DEBUG SESSION LISTING FOR AGENT {agent_id} ===")

        # Test 1: Check if agent exists
        client = get_client_from_request(request)
        try:
            agent = await client.agents.retrieve(agent_id=agent_id)
            log.info(f"✅ Agent exists: {agent.agent_id}")
        except Exception as e:
            log.error(f"❌ Agent not found: {e}")
            return {"error": f"Agent not found: {e}"}

        # Test 2: Check session resource type
        session_resource = client.agents.session
        log.info(f"Session resource type: {type(session_resource)}")
        log.info(
            "Session resource methods: "
            f"{[m for m in dir(session_resource) if not m.startswith('_')]}"
        )

        # Test 3: Try to call list method
        try:
            sessions_response = await client.agents.session.list(agent_id=agent_id)
            log.info("✅ List method called successfully")
            log.info(f"Response type: {type(sessions_response)}")
            log.info(f"Response value: {sessions_response}")
            log.info(f"Response dir: {dir(sessions_response)}")

            # Try to extract sessions
            if hasattr(sessions_response, "sessions"):
                sessions = sessions_response.sessions
                log.info(f"Found sessions attr: {sessions}")
            elif isinstance(sessions_response, list):
                sessions = sessions_response
                log.info(f"Response is direct list: {sessions}")
            else:
                sessions = []
                log.info("No sessions found in response")

            return {
                "agent_id": agent_id,
                "response_type": str(type(sessions_response)),
                "response_value": str(sessions_response),
                "sessions_count": len(sessions) if sessions else 0,
                "sessions": sessions if sessions else [],
            }

        except Exception as e:
            log.error(f"❌ List method failed: {e}")
            log.error(f"Exception type: {type(e)}")
            return {"error": f"List method failed: {e}"}

    except Exception as e:
        log.error(f"❌ Debug failed: {e}")
        return {"error": f"Debug failed: {e}"}
