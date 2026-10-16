"""Persistent entry teams, distinct from immutable draw-version snapshots.

All writes require the tournament row lock. A unique seat constraint provides a
second guard against duplicate occupants; draw creation never pairs players.
"""
import secrets
from fastapi import HTTPException
from sqlalchemy import select, delete
from app.models.models import TournamentEntryTeam, TournamentRegistration
from app.schemas.tournament import TournamentConfig


def size(t):
    return 1 if TournamentConfig.model_validate(t.config).discipline == "singles" else 2


async def teams(db, t):
    return list((await db.scalars(select(TournamentEntryTeam).where(
        TournamentEntryTeam.tournament_id == t.id).order_by(
        TournamentEntryTeam.group_no, TournamentEntryTeam.position))).all())


async def create(db, t):
    if not t.config:
        return
    cfg = TournamentConfig.model_validate(t.config)
    count = t.max_participants // size(t)
    for group in range(1, cfg.group_count + 1):
        capacity = count // cfg.group_count + int(group <= count % cfg.group_count)
        for position in range(1, capacity + 1):
            db.add(TournamentEntryTeam(tournament_id=t.id, group_no=group, position=position))
    await db.flush()


async def rebuild(db, t):
    await db.execute(delete(TournamentEntryTeam).where(TournamentEntryTeam.tournament_id == t.id))
    await create(db, t)


async def clear_partner(db, t, r):
    if r.partner_user_id:
        mate = await db.scalar(select(TournamentRegistration).where(
            TournamentRegistration.tournament_id == t.id,
            TournamentRegistration.user_id == r.partner_user_id))
        if mate:
            mate.partner_user_id = None
            mate.invite_token = secrets.token_urlsafe(24) if TournamentConfig.model_validate(t.config).pairing == "fixed" else None
    r.partner_user_id = None


async def release(db, t, r):
    await clear_partner(db, t, r)
    r.entry_team_id = r.entry_seat = None
    r.invite_token = None


async def claim(db, t, r, team_id=None, seat=None):
    cfg = TournamentConfig.model_validate(t.config)
    candidates = await teams(db, t)
    occupants = list((await db.scalars(select(TournamentRegistration).where(
        TournamentRegistration.tournament_id == t.id,
        TournamentRegistration.entry_team_id.is_not(None)).with_for_update()
        .execution_options(populate_existing=True))).all())
    others = [p for p in occupants if p is not r and p.user_id != r.user_id]
    occupied = {(p.entry_team_id, p.entry_seat) for p in others}
    if team_id is not None:
        team = next((x for x in candidates if x.id == team_id), None)
        if not team or seat not in range(1, size(t) + 1):
            raise HTTPException(422, "请选择本比赛有效的队伍空位")
        if (team_id, seat) in occupied:
            raise HTTPException(409, "该位置已有人报名，请选择其他空位")
        if cfg.discipline == "mixed" and r.gender != ("male" if seat == 1 else "female"):
            raise HTTPException(422, "混双每队一男一女，请选择对应性别的空位")
    else:
        choices = [(x, n) for x in candidates for n in range(1, size(t) + 1)
                   if (not r.requested_group or x.group_no == r.requested_group)
                   and (x.id, n) not in occupied
                   and (cfg.discipline != "mixed" or r.gender == ("male" if n == 1 else "female"))]
        if not choices:
            raise HTTPException(409, "该组队伍名额已满")
        # Fill an existing team first. Within that priority, balance automatic
        # groups, then choose a team randomly; this happens before the draw.
        partial = [(x, n) for x, n in choices if any(p.entry_team_id == x.id for p in others)]
        choices = partial or choices
        if not r.requested_group:
            counts = {g: sum(p.requested_group == g for p in others) for g in range(1, cfg.group_count + 1)}
            least = min(counts[x.group_no] for x, _ in choices)
            choices = [(x, n) for x, n in choices if counts[x.group_no] == least]
        team, seat = secrets.choice(choices)
        team_id = team.id
    await clear_partner(db, t, r)
    r.entry_team_id, r.entry_seat = team_id, seat
    r.requested_group = team.group_no
    mate = next((p for p in others if p.entry_team_id == team_id), None)
    if mate:
        r.partner_user_id, mate.partner_user_id = mate.user_id, r.user_id
        r.invite_token = mate.invite_token = None
    elif cfg.pairing == "fixed":
        r.invite_token = secrets.token_urlsafe(24)
    await db.flush()


async def available(db, t, r):
    if r.entry_team_id:
        return True
    cfg = TournamentConfig.model_validate(t.config)
    occupied = set((await db.execute(select(TournamentRegistration.entry_team_id, TournamentRegistration.entry_seat).where(
        TournamentRegistration.tournament_id == t.id, TournamentRegistration.entry_team_id.is_not(None)).with_for_update())).all())
    return any((team.id, seat) not in occupied
               and (not r.requested_group or team.group_no == r.requested_group)
               and (cfg.discipline != "mixed" or r.gender == ("male" if seat == 1 else "female"))
               for team in await teams(db, t) for seat in range(1, size(t) + 1))


def ready(t, entry_teams, registrations, eligible):
    if any(eligible(r) and not r.entry_team_id for r in registrations):
        raise ValueError("还有参赛者尚未加入队伍")
    result = []
    for team in entry_teams:
        members = sorted([r for r in registrations if r.entry_team_id == team.id], key=lambda r: r.entry_seat)
        if not members:
            continue
        if len(members) != size(t) or not all(eligible(r) for r in members):
            raise ValueError(f"第{team.group_no}组第{team.position}队尚未组队完成或队员报名未确认")
        result.append(dict(entry_team_id=team.id, group_no=team.group_no,
                           user_ids=[r.user_id for r in members]))
    cfg = TournamentConfig.model_validate(t.config)
    if any(sum(x["group_no"] == g for x in result) < 2 for g in range(1, cfg.group_count + 1)):
        raise ValueError("每组至少需要两支已完成报名的队伍")
    return result
