"""Display labels for city and zone ids (used by the recruiter dashboard, spec 006)."""

import pytest
from httpx import AsyncClient


@pytest.mark.anyio
async def test_area_labels_map_config_ids_to_display_names(client: AsyncClient) -> None:
    response = await client.get("/api/meta/areas")
    assert response.status_code == 200
    body = response.json()
    assert body["cities"]["madrid"] == "Madrid"
    assert body["zones"]["mad-chamberi"] == "Chamberí"
    assert body["zones"]["bcn-eixample"] == "Eixample"


@pytest.mark.anyio
async def test_area_labels_in_english(client: AsyncClient) -> None:
    response = await client.get("/api/meta/areas", params={"lang": "en"})
    assert response.status_code == 200
    assert response.json()["cities"]["madrid"] == "Madrid"
