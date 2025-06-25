"""
FastAPI main application module for AI Virtual Assistant.

This module initializes the FastAPI application, configures middleware,
registers API routes, and handles static file serving for the frontend.
The app provides a complete REST API for managing virtual assistants,
knowledge bases, tools, and chat interactions.
"""

import asyncio
import sys
import time
from contextlib import asynccontextmanager

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from kubernetes import client, config
from starlette.exceptions import HTTPException as StarletteHTTPException

from .database import AsyncSessionLocal
from .routes import (
    chat_sessions,
    guardrails,
    knowledge_bases,
    llama_stack,
    mcp_servers,
    model_servers,
    tools,
    users,
    validate,
    virtual_assistants,
)
from .utils.logging_config import get_logger, setup_logging

config.load_incluster_config()
core_v1 = client.CoreV1Api()

# from contextlib import asynccontextmanager

load_dotenv()

# Configure centralized logging
setup_logging(level="INFO")
logger = get_logger(__name__)


def get_incluster_namespace():
    try:
        with open("/var/run/secrets/kubernetes.io/serviceaccount/namespace") as file:
            return file.read().strip()
    except Exception:
        return "default"


async def after_serving_starts():
    await asyncio.sleep(1)  # Small delay to ensure server is serving
    print("🚀 Post-startup task: FastAPI is now serving!")

    service_name = "ai-virtual-assistant-authenticated"
    namespace = get_incluster_namespace()
    if wait_for_service_ready(service_name, namespace):
        print("Service is ready, proceeding with operations.")
        try:
            async with AsyncSessionLocal() as session:
                await mcp_servers.sync_mcp_servers(session)
        except Exception as e:
            logger.error(f"Failed to sync MCP servers on startup: {str(e)}")

        async with AsyncSessionLocal() as session:
            try:
                await model_servers.sync_model_servers(session)
            except Exception as e:
                logger.error(f"Failed to sync model servers on startup: {str(e)}")

        async with AsyncSessionLocal() as session:
            try:
                await knowledge_bases.sync_knowledge_bases(session)
            except Exception as e:
                logger.error(f"Failed to sync knowledge bases on startup: {str(e)}")
    else:
        print("Service did not become ready within the timeout.")


def wait_for_service_ready(
    service_name, namespace, timeout_seconds=300, interval_seconds=5
):
    start_time = time.time()
    while time.time() - start_time < timeout_seconds:
        try:
            endpoints = core_v1.read_namespaced_endpoints(
                name=service_name, namespace=namespace
            )
            if endpoints.subsets:
                for subset in endpoints.subsets:
                    if subset.addresses:
                        print(
                            f"Service '{service_name}' in namespace '{namespace}' \
                                is ready."
                        )
                        return True
        except client.ApiException as e:
            if e.status != 404:  # Ignore 404 if service not yet created
                print(f"Error checking endpoints: {e}")

        print(
            f"Waiting for service '{service_name}' in namespace '{namespace}' \
                to be ready..."
        )
        time.sleep(interval_seconds)

    print(f"Timeout waiting for service '{service_name}' in namespace '{namespace}'.")
    return False


async def wait_until_serving():
    url = "http://localhost:8000/"  # must match your actual host/port
    async with httpx.AsyncClient() as client:
        for _ in range(20):  # wait up to ~10s
            try:
                r = await client.get(url)
                if r.status_code == 200:
                    break
            except Exception:
                pass
            await asyncio.sleep(0.5)

    print("🚀 Server is now accepting connections!")

    # your actual post-startup function here
    await after_serving_starts()


# Use lifespan to run it right after mount
@asynccontextmanager
async def lifespan(app: FastAPI):
    # ✅ After mount happens — run post-mount async logic
    asyncio.create_task(wait_until_serving())
    yield


# app = FastAPI(lifespan=lifespan)
app = FastAPI()

origins = ["*"]  # Update this with the frontend domain in production

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(validate.router)
app.include_router(users.router, prefix="/api")
app.include_router(mcp_servers.router, prefix="/api")
app.include_router(tools.router, prefix="/api")
app.include_router(knowledge_bases.router, prefix="/api")
app.include_router(virtual_assistants.router, prefix="/api")
app.include_router(guardrails.router, prefix="/api")
app.include_router(model_servers.router, prefix="/api")
app.include_router(llama_stack.router, prefix="/api")
app.include_router(chat_sessions.router, prefix="/api")


# Serve React App (frontend)
class SPAStaticFiles(StaticFiles):
    """
    Custom static file handler for Single Page Application routing.

    Handles dev mode proxying to React dev server and production fallback
    to index.html for client-side routing.
    """

    async def get_response(self, path: str, scope):
        if len(sys.argv) > 1 and sys.argv[1] == "dev":
            # We are in Dev mode, proxy to the React dev server
            async with httpx.AsyncClient() as client:
                response = await client.get(f"http://localhost:8000/{path}")
            return Response(response.text, status_code=response.status_code)
        else:
            try:
                return await super().get_response(path, scope)
            except (HTTPException, StarletteHTTPException) as ex:
                if ex.status_code == 404:
                    return await super().get_response("index.html", scope)
                else:
                    raise ex


app.mount(
    "/", SPAStaticFiles(directory="backend/public", html=True), name="spa-static-files"
)
