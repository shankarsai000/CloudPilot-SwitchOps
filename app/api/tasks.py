"""
CloudPilot SwitchOps — Tasks & Switch Event API Endpoints

Provides read-only queries for tasks, append-only event histories, and evidence,
plus an operational diagnostic simulation endpoint for developer verification.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.core.errors import TaskNotFoundError
from app.domain.models import Evidence, Task, TaskEvent, TaskStatus
from app.services.task_service import TaskService

router = APIRouter(prefix="/api/v1", tags=["Tasks & Audit"])


def get_task_service() -> TaskService:
    raise NotImplementedError


class SimulateMessageRequest(BaseModel):
    """Payload for developer diagnostic testing of Switch room interactions."""
    room_id: str = Field(default="cloudpilot-ops", description="Target Switch room ID")
    text: str = Field(
        default="@CloudPilot review the staging infrastructure for a cost and security assessment. Do not modify any files or infrastructure.",
        description="Message content addressing CloudPilot",
    )
    sender: str = Field(default="@operator:switch", description="Simulated participant identity")
    sender_name: str = Field(default="DevOps Engineer", description="Simulated participant name")


@router.get("/tasks/{task_id}", response_model=Task, summary="Get Task by ID")
def get_task_endpoint(
    task_id: str,
    service: TaskService = Depends(get_task_service),
) -> Task:
    """Retrieve full task state and metadata by task ID."""
    try:
        return service.get_task(task_id)
    except TaskNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=exc.to_dict())


@router.get("/tasks", response_model=list[Task], summary="List Tasks")
def list_tasks_endpoint(
    status: TaskStatus | None = Query(None, description="Filter by status"),
    room_id: str | None = Query(None, description="Filter by Switch room ID"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    service: TaskService = Depends(get_task_service),
) -> list[Task]:
    """List tasks chronologically with status and room filters."""
    return service.list_tasks(status=status, room_id=room_id, limit=limit, offset=offset)


@router.get("/tasks/{task_id}/events", response_model=list[TaskEvent], summary="Get Task Audit Events")
def get_task_events_endpoint(
    task_id: str,
    service: TaskService = Depends(get_task_service),
) -> list[TaskEvent]:
    """Retrieve the immutable, append-only audit trail for a task."""
    try:
        return service.get_task_events(task_id)
    except TaskNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=exc.to_dict())


@router.get("/tasks/{task_id}/evidence", response_model=list[Evidence], summary="Get Task Evidence Findings")
def get_task_evidence_endpoint(
    task_id: str,
    service: TaskService = Depends(get_task_service),
) -> list[Evidence]:
    """Retrieve all evidence records associated with a task."""
    try:
        return service.get_task_evidence(task_id)
    except TaskNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=exc.to_dict())


@router.post("/switch/simulate-message", response_model=Task, summary="Simulate Switch Room Message (Developer Diagnostics)")
async def simulate_switch_message(
    req: SimulateMessageRequest,
    service: TaskService = Depends(get_task_service),
) -> Task:
    """
    Developer diagnostic endpoint.
    Emulates an incoming addressed message from a Switch room and triggers the
    full Task lifecycle: RECEIVED -> ACKNOWLEDGED -> IN_PROGRESS -> COMPLETED,
    including room acknowledgment and result posting.
    """
    frame = {
        "event": "message",
        "rooms": [req.room_id],
        "payload": {
            "addressed": True,
            "sender": req.sender,
            "sender_name": req.sender_name,
            "body": req.text,
            "timestamp": 1730000000000,
        },
    }
    task = await service.handle_switch_event(frame)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "Message could not be processed as a CloudPilot task."},
        )
    return task
