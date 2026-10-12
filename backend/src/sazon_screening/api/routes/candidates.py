"""Recruiter dashboard (FR-6..10): list, export, detail, summary and recruiter actions.

Opted-out candidates need no special case here: the engine purged their fields and the
service redacted their transcript, so there is no PII left to show (002 FR-11).
"""

import csv
import io
from typing import Annotated

from fastapi import APIRouter, Depends, Response

from sazon_screening.api import repo
from sazon_screening.api.deps import ServiceDep, SessionDep
from sazon_screening.api.repo import CandidateFilters, SortKey
from sazon_screening.api.schemas import (
    ActionIn,
    ActionOut,
    CandidateDetail,
    CandidateRow,
    MessageOut,
    RecruiterStatus,
    SummaryOut,
    TraceOut,
)
from sazon_screening.api.service import ConversationNotFound
from sazon_screening.engine import CandidateRecord
from sazon_screening.vocab import Bucket, Country, Language, Status

router = APIRouter(prefix="/api/candidates", tags=["recruiter dashboard"])


def candidate_filters(
    status: Status | None = None,
    country: Country | None = None,
    city: str | None = None,
    bucket: Bucket | None = None,
    recruiter_status: RecruiterStatus | None = None,
    q: str | None = None,
    sort: SortKey = "-updated",
) -> CandidateFilters:
    return CandidateFilters(
        status=status,
        country=country,
        city=city,
        bucket=bucket,
        recruiter_status=recruiter_status,
        q=q,
        sort=sort,
    )


FiltersDep = Annotated[CandidateFilters, Depends(candidate_filters)]


@router.get("")
async def list_candidates(filters: FiltersDep, session: SessionDep) -> list[CandidateRow]:
    return [CandidateRow.of(row) for row in await repo.list_candidates(session, filters)]


@router.get("/export.csv", response_class=Response)
async def export_csv(filters: FiltersDep, session: SessionDep) -> Response:
    rows = [CandidateRow.of(row) for row in await repo.list_candidates(session, filters)]
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=list(CandidateRow.model_fields))
    writer.writeheader()
    for row in rows:
        values = row.model_dump(mode="json")
        writer.writerow({k: ";".join(v) if isinstance(v, list) else v for k, v in values.items()})
    return Response(
        content=out.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="candidates.csv"'},
    )


@router.get("/{conversation_id}")
async def get_candidate(
    conversation_id: str, session: SessionDep, service: ServiceDep
) -> CandidateDetail:
    row = await repo.get_conversation(session, conversation_id)
    if row is None:
        raise ConversationNotFound(conversation_id)
    messages = await repo.list_messages(session, conversation_id)
    language = service.default_summary_language.value
    summary = await repo.get_summary(session, conversation_id, language)
    traces = [TraceOut.of(m) for m in messages]
    return CandidateDetail(
        candidate=CandidateRow.of(row),
        record=CandidateRecord.model_validate(row.record_json),
        summary=SummaryOut.of(summary) if summary else None,
        transcript=[MessageOut.of(m) for m in messages],
        traces=[t for t in traces if t is not None],
        actions=[ActionOut.of(a) for a in await repo.list_actions(session, conversation_id)],
    )


@router.get("/{conversation_id}/summary")
async def get_summary(
    conversation_id: str, service: ServiceDep, lang: Language | None = None
) -> SummaryOut:
    """FR-8: stored, or generated once and stored. 409 while the conversation is running."""
    row = await service.summary(conversation_id, lang or service.default_summary_language)
    return SummaryOut.of(row)


@router.post("/{conversation_id}/actions", status_code=201)
async def add_action(conversation_id: str, body: ActionIn, service: ServiceDep) -> ActionOut:
    return ActionOut.of(await service.record_action(conversation_id, body.action, body.note))
