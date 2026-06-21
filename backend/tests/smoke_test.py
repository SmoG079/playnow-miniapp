#!/usr/bin/env python3
"""Quick API smoke tests — run from backend/ directory"""
import asyncio
import httpx

BASE = "http://127.0.0.1:8000/api/v1"

TOKEN = None  # set after login


async def test(label, method, path, data=None, auth=True, expect=200):
    headers = {}
    if auth and TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
    url = f"{BASE}{path}"
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.request(method, url, json=data, headers=headers)
    status = "✅" if r.status_code == expect else "❌"
    detail = r.text[:300] if r.status_code != expect else ""
    print(f"{status} [{r.status_code}] {method} {path} {detail}")
    return r


async def main():
    global TOKEN

    # 1. Health (root level, not under /api/v1)
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get("http://127.0.0.1:8000/health")
        print(f"{'✅' if r.status_code==200 else '❌'} [{r.status_code}] GET /health")

    # 2. Club list (public)
    r = await test("club list", "GET", "/clubs", auth=False, expect=200)
    clubs = r.json().get("items", []) if r.status_code == 200 else []
    print(f"   Found {len(clubs)} clubs")

    # 3. Club detail + venues
    if clubs:
        cid = clubs[0]["id"]
        r = await test("club detail", "GET", f"/clubs/{cid}", auth=False, expect=200)
        club = r.json() if r.status_code == 200 else {}
        venues = club.get("venues", [])
        print(f"   Club '{club.get('name')}' has {len(venues)} venues")

        # 4. Venue slots
        if venues:
            vid = venues[0]["id"]
            from datetime import date
            today = date.today().isoformat()
            r = await test("slots", "GET",
                           f"/venues/{vid}/slots?date_from={today}&date_to={today}",
                           auth=False, expect=200)
            slot_groups = r.json() if r.status_code == 200 else []
            slot_count = sum(len(g['slots']) for g in slot_groups)
            print(f"   Venue {vid}: {slot_count} slots on {today}")

    # 5. Posts
    await test("posts", "GET", "/posts", auth=False, expect=200)

    print("\nDone.")


asyncio.run(main())
