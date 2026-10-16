"""Interviews (spec 010): the candidate's calendar invite, and the recruiters' agenda."""

from fastapi import APIRouter, HTTPException, Response

from sazon_screening.api.deps import ServiceDep

router = APIRouter(prefix="/api/interviews", tags=["interviews"])


@router.get(
    "/{conversation_id}.ics",
    response_class=Response,
    responses={200: {"content": {"text/calendar": {}}}, 404: {"description": "No interview"}},
)
async def interview_ics(conversation_id: str, service: ServiceDep) -> Response:
    """FR-5: the booked interview as an iCalendar invite (candidate and recruiter). 404 when
    the conversation does not exist or has no booked interview."""
    ics = await service.interview_ics(conversation_id)
    if ics is None:
        raise HTTPException(status_code=404, detail="No booked interview")
    return Response(
        content=ics,
        media_type="text/calendar; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="entrevista-grupo-sazon.ics"'},
    )
