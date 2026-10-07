from datetime import datetime
import pytest
from app.schemas.tournament import TournamentConfig, TournamentCreate
from app.services import tournament_engine as e


@pytest.mark.parametrize("count", [2, 3, 4, 5, 6, 7, 8, 16, 31, 64])
def test_knockout_byes_and_advancement(count):
    matches = e.knockout(list(range(1, count + 1)), third_place=True)
    first = [m for m in matches if m["round_no"] == 1]
    assert all(m.get("team_a_id") or m.get("team_b_id") for m in first)
    assert (
        sum(m["status"] == "bye" for m in first)
        == (1 << (count - 1).bit_length()) - count
    )
    for m in matches:
        if m["status"] == "pending":
            assert m.get("team_a_id") and m.get("team_b_id")
            m["status"] = "completed"
            m["winner_id"] = m["team_a_id"]
            e.resolve(matches)
    assert all(m["status"] in ("completed", "bye") for m in matches)
    assert (
        sum(m["status"] == "completed" for m in matches if m["kind"] == "knockout")
        == count - 1
    )


@pytest.mark.parametrize("count", [3, 4, 5, 8, 15])
def test_round_robin_every_pair_once_and_no_overlap(count):
    ms = e.round_robin(list(range(count)))
    assert len(ms) == count * (count - 1) // 2
    assert len({frozenset((m["team_a_id"], m["team_b_id"])) for m in ms}) == len(ms)
    for r in {m["round_no"] for m in ms}:
        ids = [
            t
            for m in ms
            if m["round_no"] == r
            for t in (m["team_a_id"], m["team_b_id"])
        ]
        assert len(ids) == len(set(ids))
    c = TournamentConfig(format="round_robin", courts=["一", "二"], max_parallel=1)
    e.schedule(ms, c, datetime(2026, 10, 10))
    assert all(m["court"] == "一" for m in ms)
    for a in ms:
        for b in ms:
            if (
                a is not b
                and a["scheduled_at"] < b["scheduled_end"]
                and b["scheduled_at"] < a["scheduled_end"]
            ):
                assert a["court"] != b["court"]
                assert not {a["team_a_id"], a["team_b_id"]} & {
                    b["team_a_id"],
                    b["team_b_id"],
                }


def test_fixed_and_random_mixed_pairing():
    p = [
        dict(user_id=1, gender="male", pairing="fixed", partner_user_id=2),
        dict(user_id=2, gender="female", pairing="fixed", partner_user_id=1),
        dict(user_id=3, gender="male"),
        dict(user_id=4, gender="female"),
    ]
    assert e.pair_players(p, "mixed", "s") == [[1, 2], [3, 4]]
    with pytest.raises(ValueError):
        e.pair_players(p[:-1], "mixed", "s")
    p[0]["partner_user_id"] = None
    with pytest.raises(ValueError):
        e.pair_players(p, "mixed", "s")


def test_head_to_head_tie_and_manual_order():
    ms = e.round_robin([1, 2, 3])
    for m in ms:
        m.update(
            status="completed",
            winner_id={
                frozenset((1, 2)): 1,
                frozenset((2, 3)): 2,
                frozenset((1, 3)): 3,
            }[frozenset((m["team_a_id"], m["team_b_id"]))],
        )
    assert all(r["tie_unresolved"] for r in e.standings([1, 2, 3], ms))
    rows = e.standings([1, 2, 3], ms, [3, 1, 2])
    assert [r["team_id"] for r in rows] == [3, 1, 2]
    assert all(not r["tie_unresolved"] for r in rows)


def test_qualified_draw_avoids_group_rematch_with_byes():
    ids = [1, 2, 3, 4, 5, 6]
    origins = {1: 1, 2: 1, 3: 2, 4: 2, 5: 3, 6: 3}
    ms = e.qualified_draw(ids, origins, "fixed", True)
    for m in ms:
        if m["round_no"] == 1 and m.get("team_a_id") and m.get("team_b_id"):
            assert origins[m["team_a_id"]] != origins[m["team_b_id"]]


def test_validation_and_timezone():
    t = TournamentCreate(
        address="测试网球场",
        club_id=1,
        title="测试",
        max_participants=16,
        start_time="2026-10-11T09:00:00+08:00",
        end_time="2026-10-12T09:00:00+08:00",
        config=TournamentConfig(),
    )
    assert t.start_time.hour == 1 and t.registration_deadline == t.start_time
    assert t.cancellation_deadline.hour == 0
    with pytest.raises(ValueError):
        TournamentConfig(courts=["重复", "重复"])
    with pytest.raises(ValueError):
        TournamentCreate(
        address="测试网球场",
            club_id=1,
            title="测试",
            start_time=t.start_time,
            end_time=t.end_time,
            max_participants=5,
            config=TournamentConfig(discipline="doubles"),
        )
