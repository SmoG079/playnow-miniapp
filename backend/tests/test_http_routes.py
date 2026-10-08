"""Exercise static resource routes through HTTP, including their access checks."""
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.api.v1 import users, bookings, venues, auth
from app.api.deps import get_current_user
from app.core.database import get_db
from datetime import date, time
from decimal import Decimal


class StaticRouteTests(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        app.include_router(users.router, prefix="/api/v1")
        app.include_router(bookings.router, prefix="/api/v1")
        app.include_router(venues.router, prefix="/api/v1")
        app.include_router(auth.router, prefix="/api/v1")
        self.app = app
        self.user = SimpleNamespace(id=1, role="platform_admin")
        result = SimpleNamespace(scalar=lambda: 0, all=lambda: [],
            scalar_one_or_none=lambda: None, one_or_none=lambda: None)
        self.db = SimpleNamespace(execute=AsyncMock(return_value=result))
        async def database():
            yield self.db
        app.dependency_overrides[get_current_user] = lambda: self.user
        app.dependency_overrides[get_db] = database
        self.client = TestClient(app)

    def test_unread_count_is_not_treated_as_notification_id(self):
        response = self.client.get("/api/v1/users/me/notifications/unread-count")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), {"count": 0})
        self.db.execute.assert_awaited_once()

    def test_settlements_list_remains_accessible_to_platform_admin(self):
        response = self.client.get("/api/v1/bookings/settlements")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["items"], [])
        self.assertEqual(response.json()["total"], 0)

    def test_settlements_list_still_refuses_regular_users(self):
        self.user.role = "user"
        response = self.client.get("/api/v1/bookings/settlements")
        self.assertEqual(response.status_code, 403, response.text)
        self.db.execute.assert_not_awaited()

    def test_integer_detail_routes_still_reach_their_handlers(self):
        for route in ["/api/v1/bookings/123", "/api/v1/users/me/notifications/123"]:
            response = self.client.get(route)
            self.assertEqual(response.status_code, 404, response.text)
            self.assertIn("not found", response.json()["detail"].lower())

    def test_missing_auth_header_returns_401_before_querying_user(self):
        del self.app.dependency_overrides[get_current_user]
        response = self.client.get("/api/v1/users/me")
        self.assertEqual(response.status_code, 401, response.text)
        self.db.execute.assert_not_awaited()

    def test_production_refuses_development_login_without_database_access(self):
        with patch.object(auth.settings, "DEBUG", False):
            response = self.client.post("/api/v1/auth/login", json={"code": "dev_fixture"})
        self.assertEqual(response.status_code, 400, response.text)
        self.db.execute.assert_not_awaited()

    def test_production_refuses_mock_phone_authorization(self):
        self.db.commit = AsyncMock()
        with patch.object(auth.settings, "DEBUG", False):
            response = self.client.post("/api/v1/auth/phone", json={"code": "dev_fixture"})
        self.assertEqual(response.status_code, 400, response.text)
        self.db.commit.assert_not_awaited()

    def test_slot_date_range_and_default_venue_price(self):
        slot = SimpleNamespace(id=7, venue_id=9, date=date(2026, 10, 14),
            start_time=time(8), end_time=time(9), price_override=None,
            status="available", venue=SimpleNamespace(price_per_hour=Decimal("120")))
        self.db.execute.return_value = SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: [slot]))
        response = self.client.get("/api/v1/venues/9/slots?date_from=2026-10-14&date_to=2026-10-14")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()[0]["date"], "2026-10-14")
        self.assertEqual(Decimal(response.json()[0]["slots"][0]["price"]), Decimal("120"))
        slot.price_override = Decimal("90")
        response = self.client.get("/api/v1/venues/9/slots?date=2026-10-14")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(Decimal(response.json()[0]["slots"][0]["price"]), Decimal("90"))


if __name__ == "__main__":
    unittest.main()
