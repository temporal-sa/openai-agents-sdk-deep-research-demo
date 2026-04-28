"""
FastAPI Backend for Temporal Research UI
=========================================
Production-ready backend connecting to Temporal workflows.

Environment Variables:
- TEMPORAL_PROFILE: name of the env config profile to use (optional).
- TEMPORAL_ADDRESS: Temporal server address (default: 127.0.0.1:7233)
- TEMPORAL_NAMESPACE: Temporal namespace (default: default)
- TEMPORAL_API_KEY: API key for Temporal Cloud (disabled by default)
- TEMPORAL_TASK_QUEUE: Task queue name (default: research-queue)
"""

import os
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Dict, List, Optional

from dotenv import load_dotenv
from fastapi import APIRouter, Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from temporalio.client import Client, WorkflowUpdateStage
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.envconfig import ClientConfig

from openai_agents.workflows.interactive_research_workflow import (
    InteractiveResearchResult,
    InteractiveResearchWorkflow,
)
from openai_agents.workflows.research_agents.research_models import (
    SingleClarificationInput,
    UserQueryInput,
)
from auth import _ensure_firebase_initialized, verify_firebase_user

# Load environment variables
load_dotenv()

TEMPORAL_TASK_QUEUE = os.getenv("TEMPORAL_TASK_QUEUE", "research-queue")


def get_temporal_ui_base_url() -> str:
    """Build the Temporal UI base URL for workflow links."""
    host = temporal_config.get("target_host", "localhost:7233")
    namespace = temporal_config.get("namespace", "default")
    if "localhost" in host or "127.0.0.1" in host:
        return f"http://localhost:8233/namespaces/{namespace}/workflows"
    return f"https://cloud.temporal.io/namespaces/{namespace}/workflows"


# ============================================
# FastAPI App Setup
# ============================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Eagerly initialize Firebase so misconfigured deploys fail loudly at boot."""
    if os.getenv("AUTH_DISABLED", "").lower() == "true":
        print("[auth] AUTH_DISABLED=true — skipping Firebase initialization")
    else:
        _ensure_firebase_initialized()
    yield


app = FastAPI(
    title="Temporal Research API",
    description="Backend API for the Temporal Research Demo UI",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware for frontend.
# FRONTEND_ORIGINS is a comma-separated list set at deploy time; default "*" for dev.
_frontend_origins = [o.strip() for o in os.getenv("FRONTEND_ORIGINS", "*").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_frontend_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# All /api/* routes (except /api/health) are gated by Firebase auth.
api = APIRouter(prefix="/api", dependencies=[Depends(verify_firebase_user)])

# ============================================
# Temporal Client Setup
# ============================================


temporal_client: Optional[Client] = None

temporal_config = ClientConfig.load_client_connect_config()
temporal_config.setdefault("target_host", "localhost:7233")
temporal_config.setdefault("namespace", "default")


async def get_temporal_client() -> Client:
    global temporal_client
    if temporal_client:
        return temporal_client

    print(
        f"Connecting to Temporal at {temporal_config.get('target_host')} in namespace {temporal_config.get('namespace')}"
    )

    temporal_client = await Client.connect(
        **temporal_config,
        data_converter=pydantic_data_converter,
    )
    return temporal_client


# ============================================
# Request/Response Models
# ============================================
class StartResearchRequest(BaseModel):
    query: str


class AnswerRequest(BaseModel):
    answer: str


class WorkflowStatusResponse(BaseModel):
    workflow_id: str
    status: str  # "pending", "awaiting_clarifications", "researching", "complete"
    original_query: Optional[str] = None
    current_question: Optional[str] = None
    current_question_index: int = 0
    total_questions: int = 0
    clarification_responses: Dict[str, str] = {}


class ResearchResultResponse(BaseModel):
    workflow_id: str
    markdown_report: str
    short_summary: str
    follow_up_questions: List[str]


# ============================================
# Static File Serving
# ============================================
@app.get("/")
async def serve_index():
    """Serve the main chat interface"""
    index_path = Path(__file__).parent.parent / "index.html"
    if index_path.exists():
        return HTMLResponse(content=index_path.read_text())
    raise HTTPException(status_code=404, detail="Index page not found")


@app.get("/success")
async def serve_success():
    """Serve the success/results page"""
    success_path = Path(__file__).parent.parent / "success.html"
    if success_path.exists():
        return HTMLResponse(content=success_path.read_text())
    raise HTTPException(status_code=404, detail="Success page not found")


# Serve static assets (JS, CSS, fonts, images)
static_path = Path(__file__).parent.parent
if static_path.exists():
    app.mount("/static", StaticFiles(directory=str(static_path)), name="static")

images_path = Path(__file__).resolve().parent.parent.parent / "temp_images"
images_path.mkdir(exist_ok=True)
app.mount("/temp_images", StaticFiles(directory=str(images_path)), name="images")

# ============================================
# API Endpoints
# ============================================


@api.post("/start-research")
async def start_research(request: StartResearchRequest):
    """
    Start a new research workflow.

    Returns:
        workflow_id: Unique identifier for tracking the workflow
        status: Initial status ("started")
    """
    client = await get_temporal_client()
    workflow_id = f"interactive-research-{uuid.uuid4().hex[:8]}"

    await client.start_workflow(
        InteractiveResearchWorkflow.run,
        args=[None, False],
        id=workflow_id,
        task_queue=TEMPORAL_TASK_QUEUE,
    )

    return {
        "workflow_id": workflow_id,
        "status": "started",
        "temporal_ui_url": f"{get_temporal_ui_base_url()}/{workflow_id}",
    }


@api.post("/initialize/{workflow_id}")
async def initialize_research(workflow_id: str, request: StartResearchRequest):
    """Send the start_research update to an already-started workflow."""
    client = await get_temporal_client()
    handle = client.get_workflow_handle(workflow_id)
    await handle.start_update(
        InteractiveResearchWorkflow.start_research,
        UserQueryInput(query=request.query.strip()),
        wait_for_stage=WorkflowUpdateStage.ACCEPTED,
    )
    return {"status": "accepted"}


@api.get("/status/{workflow_id}")
async def get_status(workflow_id: str):
    """
    Get current workflow status.

    Returns:
        workflow_id: Workflow identifier
        status: Current status (awaiting_clarifications, researching, completed)
        current_question: The clarification question to display (if awaiting)
        current_question_index: Index of current question
        total_questions: Total number of clarification questions
    """
    client = await get_temporal_client()
    handle = client.get_workflow_handle(workflow_id)
    status = await handle.query(InteractiveResearchWorkflow.get_status)

    response = {
        "workflow_id": workflow_id,
        "status": status.status,
        "original_query": status.original_query,
        "current_question": status.current_question,
        "current_question_index": status.current_question_index,
        "total_questions": len(status.clarification_questions or []),
        "clarification_responses": status.clarification_responses or {},
    }

    if status.status == "awaiting_clarifications":
        response["current_question"] = status.get_current_question()

    return response


@api.post("/answer/{workflow_id}/{current_question_index}")
async def submit_answer(
    workflow_id: str, current_question_index: int, request: AnswerRequest
):
    """
    Submit an answer to a clarification question.

    Returns:
        status: "accepted" if answer was recorded
        workflow_status: Current workflow status after answer
        questions_remaining: Number of questions left
    """
    client = await get_temporal_client()
    handle = client.get_workflow_handle(workflow_id)

    await handle.execute_update(
        InteractiveResearchWorkflow.provide_single_clarification,
        SingleClarificationInput(
            question_index=current_question_index, answer=request.answer.strip()
        ),
    )

    status = await handle.query(InteractiveResearchWorkflow.get_status)

    return {
        "status": "accepted",
        "workflow_status": status.status,
        "questions_remaining": len(status.clarification_questions or [])
        - status.current_question_index,
    }

    raise HTTPException(
        status_code=501,
        detail="Temporal integration not configured. See backend/main.py for setup instructions.",
    )


@api.get("/result/{workflow_id}")
async def get_result(workflow_id: str):
    """
    Get final research result.

    Returns:
        workflow_id: Workflow identifier
        markdown_report: Full markdown research report
        short_summary: Brief summary of findings
        follow_up_questions: Suggested follow-up questions
    """
    client = await get_temporal_client()
    handle = client.get_workflow_handle(workflow_id)

    # Check if workflow is complete
    desc = await handle.describe()
    if not desc.status or desc.status.name != "COMPLETED":
        raise HTTPException(status_code=400, detail="Research not complete yet")

    result: InteractiveResearchResult = await handle.result()

    # return {
    #     "workflow_id": workflow_id,
    #     "markdown_report": result.markdown_report,
    #     "short_summary": result.short_summary,
    #     "follow_up_questions": result.follow_up_questions or [],
    # }

    return result


@api.get("/stream/{workflow_id}")
async def stream_status(workflow_id: str):
    """
    Server-Sent Events endpoint for live status updates.

    Streams status updates every second until workflow completes.

    NOTE: When implemented, the EventSource API cannot send Authorization
    headers, so the token will need to be passed as a short-lived query
    parameter (or migrate to fetch + ReadableStream). See ui/src/js/auth.js.
    """
    # TODO: Implement SSE streaming with Temporal
    #
    # async def event_generator():
    #     client = await get_temporal_client()
    #     handle = client.get_workflow_handle(workflow_id)
    #
    #     while True:
    #         status = await handle.query(InteractiveResearchWorkflow.get_status)
    #
    #         data = {
    #             "status": status.status,
    #             "current_question_index": status.current_question_index,
    #             "total_questions": len(status.clarification_questions or []),
    #         }
    #
    #         yield f"data: {json.dumps(data)}\n\n"
    #
    #         if status.status == "complete":
    #             break
    #
    #         await asyncio.sleep(1)
    #
    # return StreamingResponse(
    #     event_generator(),
    #     media_type="text/event-stream",
    #     headers={
    #         "Cache-Control": "no-cache",
    #         "Connection": "keep-alive",
    #     }
    # )

    raise HTTPException(
        status_code=501,
        detail="Temporal integration not configured. See backend/main.py for setup instructions.",
    )


@app.get("/api/health")
async def health_check():
    """Health check endpoint (unauthenticated, used by k8s probes)."""
    return {
        "status": "healthy",
        # "temporal_profile": TEMPORAL_PROFILE,
        "temporal_address": temporal_config.get("target_host"),
        "temporal_namespace": temporal_config.get("namespace"),
        "task_queue": TEMPORAL_TASK_QUEUE,
    }


# Mount the authenticated API router after all routes are registered.
app.include_router(api)


# ============================================
# Main Entry Point
# ============================================
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8234)
