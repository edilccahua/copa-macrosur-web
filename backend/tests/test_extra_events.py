import pytest
from httpx import AsyncClient, ASGITransport
from backend.app.main import app

@pytest.mark.asyncio
async def test_get_extra_events():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/api/v1/public/extra-events")
        assert res.status_code == 200
        data = res.json()
        assert isinstance(data, list)
        assert len(data) >= 2
        slugs = [e["slug"] for e in data]
        assert "vuelta-a-talamolle-2026" in slugs
        assert "clasica-arequipa-mollendo-72" in slugs

        # Comprobar campos ricos
        talamolle = next(e for e in data if e["slug"] == "vuelta-a-talamolle-2026")
        assert talamolle["short_name"] == "Talamolle"
        assert talamolle["event_type"] == "ROAD"
        assert "Mollebaya" in talamolle["start_location"]
        assert talamolle["whatsapp_contact"] == "994382248"
        assert "extra-vuelta-talamolle-card.webp" in talamolle["poster_url"]
