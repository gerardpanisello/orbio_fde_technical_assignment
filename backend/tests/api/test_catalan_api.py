"""Spec 017 over HTTP: a Catalan conversation, and summaries that stay es/en (FR-6)."""

import pytest
from httpx import AsyncClient

from tests.api.test_candidates import converse

CATALAN = [
    "sí, d'acord",
    "Em dic Jordi Puig",
    "tinc 24 anys",
    "cotxe",
    "sí",
    "visc a Chamberí, Madrid",
    "mitja jornada",
    "a la tarda",
    "2 anys a Glovo",
    "dilluns",
    "sí, tot correcte",
    "1",
]


@pytest.mark.anyio
@pytest.mark.ac("017:AC-1")
async def test_a_catalan_conversation_over_the_api(client: AsyncClient) -> None:
    conversation_id = await converse(client, CATALAN, language="ca", country_hint="ES")
    conversation = (await client.get(f"/api/conversations/{conversation_id}")).json()
    assert conversation["language"] == "ca"
    assert conversation["status"] == "interview_scheduled"
    rows = (await client.get("/api/candidates")).json()
    assert next(r for r in rows if r["id"] == conversation_id)["language"] == "ca"


@pytest.mark.anyio
@pytest.mark.ac("017:AC-6")
async def test_summaries_are_written_in_spanish_or_english_only(client: AsyncClient) -> None:
    conversation_id = await converse(
        client, ["sí, d'acord", "Em dic Jordi Puig", "tinc 16 anys"], language="ca"
    )
    refused = await client.get(f"/api/candidates/{conversation_id}/summary", params={"lang": "ca"})
    assert refused.status_code == 422
    spanish = await client.get(f"/api/candidates/{conversation_id}/summary")
    assert spanish.status_code == 200
    facts = {fact["key"]: fact["value"] for fact in spanish.json()["facts"]}
    assert facts["candidate_language"] == "Catalán"
