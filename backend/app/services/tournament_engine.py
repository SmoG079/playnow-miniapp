"""Pure, reproducible tournament pairing, brackets, standings and scheduling."""

from collections import defaultdict
from datetime import timedelta
import random


def knockout(teams, group=1, third_place=False):
    if len(teams) < 2:
        raise ValueError("每组至少需要两队")
    size = 1 << (len(teams) - 1).bit_length()
    slots = [None] * size
    # One entrant in every first-round match, then fill the remaining sides.
    for i, team in enumerate(teams):
        slots[2 * i if i < size // 2 else 2 * (i - size // 2) + 1] = team
    matches, previous, round_no = [], [], 1
    for i in range(size // 2):
        key = f"{group}:1:{i}"
        matches.append(
            dict(
                key=key,
                group_no=group,
                round_no=1,
                position=i,
                kind="knockout",
                team_a_id=slots[2 * i],
                team_b_id=slots[2 * i + 1],
            )
        )
        previous.append(key)
    while len(previous) > 1:
        round_no += 1
        current = []
        for i in range(len(previous) // 2):
            key = f"{group}:{round_no}:{i}"
            matches.append(
                dict(
                    key=key,
                    group_no=group,
                    round_no=round_no,
                    position=i,
                    kind="knockout",
                    source_a=previous[2 * i],
                    source_b=previous[2 * i + 1],
                )
            )
            current.append(key)
        previous = current
    if third_place and size >= 4:
        final = matches[-1]
        matches.append(
            dict(
                key=f"{group}:third",
                group_no=group,
                round_no=round_no,
                position=1,
                kind="third_place",
                source_a=final["source_a"],
                source_b=final["source_b"],
                source_outcome="loser",
            )
        )
    resolve(matches)
    return matches


def round_robin(teams, group=1):
    if len(teams) < 2:
        raise ValueError("每组至少需要两队")
    rotating = list(teams)
    if len(rotating) % 2:
        rotating.append(None)
    matches = []
    for r in range(len(rotating) - 1):
        for i in range(len(rotating) // 2):
            a, b = rotating[i], rotating[-i - 1]
            if a is not None and b is not None:
                matches.append(
                    dict(
                        key=f"{group}:{r + 1}:{i}",
                        group_no=group,
                        round_no=r + 1,
                        position=i,
                        kind="round_robin",
                        team_a_id=a,
                        team_b_id=b,
                        status="pending",
                    )
                )
        rotating = [rotating[0], rotating[-1], *rotating[1:-1]]
    return matches


def resolve(matches):
    """Resolve incoming winner/loser references. Only known empty seats count as byes."""
    by_key = {m["key"]: m for m in matches}
    for m in matches:
        ready = True
        for side in ("a", "b"):
            source = m.get(f"source_{side}")
            if source:
                parent = by_key[source]
                if parent.get("status") not in ("completed", "bye"):
                    ready = False
                    m[f"team_{side}_id"] = None
                elif m.get("source_outcome") == "loser":
                    m[f"team_{side}_id"] = next(
                        (
                            parent.get(k)
                            for k in ("team_a_id", "team_b_id")
                            if parent.get(k)
                            and parent.get(k) != parent.get("winner_id")
                        ),
                        None,
                    )
                else:
                    m[f"team_{side}_id"] = parent.get("winner_id")
        if m.get("status") == "completed":
            continue
        a, b = m.get("team_a_id"), m.get("team_b_id")
        m["status"] = "pending"
        m["winner_id"] = None
        if ready and m["kind"] != "round_robin" and (a is None or b is None):
            m["status"], m["winner_id"] = "bye", a or b
    return matches


def build(teams, config, seed):
    rng = random.Random(seed)
    teams = list(teams)
    rng.shuffle(teams)
    groups = [[] for _ in range(config.group_count)]
    for i, team in enumerate(teams):
        groups[i % len(groups)].append(team)
    generator = knockout if config.format == "knockout" else round_robin
    matches = []
    for g, group in enumerate(groups, 1):
        matches += (
            generator(group, g, config.third_place)
            if generator is knockout
            else generator(group, g)
        )
    return groups, matches


def standings(teams, matches, tie_orders=None):
    scores = {t: dict(team_id=t, points=0, wins=0, draws=0, losses=0) for t in teams}
    for m in matches:
        if m["kind"] != "round_robin" or m.get("status") != "completed":
            continue
        a, b = m["team_a_id"], m["team_b_id"]
        if m.get("is_draw"):
            for t in (a, b):
                scores[t]["points"] += 0.5
                scores[t]["draws"] += 1
        else:
            winner = m["winner_id"]
            loser = b if winner == a else a
            scores[winner]["wins"] += 1
            scores[winner]["points"] += 1
            scores[loser]["losses"] += 1
    buckets = defaultdict(list)
    for row in scores.values():
        buckets[row["points"]].append(row)
    output = []
    for points in sorted(buckets, reverse=True):
        rows = buckets[points]
        resolved = len(rows) == 1
        if len(rows) == 2:
            ids = {row["team_id"] for row in rows}
            head = next(
                (
                    m
                    for m in matches
                    if m.get("status") == "completed"
                    and {m.get("team_a_id"), m.get("team_b_id")} == ids
                    and m.get("winner_id")
                ),
                None,
            )
            if head:
                rows.sort(key=lambda row: row["team_id"] != head["winner_id"])
                resolved = True
        ids = {row["team_id"] for row in rows}
        if not resolved and tie_orders and ids.issubset(set(tie_orders)):
            rows.sort(key=lambda row: tie_orders.index(row["team_id"]))
            resolved = True
        for row in rows:
            row["tie_unresolved"] = not resolved
            row["rank"] = len(output) + 1
            output.append(row)
    return output


def pair_players(players, discipline, seed):
    rng = random.Random(seed)
    players = {p["user_id"]: p for p in players}
    if discipline == "singles":
        return [[u] for u in players]
    fixed, remaining = [], dict(players)
    for u, p in players.items():
        partner = p.get("partner_user_id")
        if p.get("pairing") == "fixed" and not partner:
            raise ValueError(f"用户 {u} 尚未确认搭档")
        if partner:
            if partner not in players or players[partner].get("partner_user_id") != u:
                raise ValueError("固定搭档必须双方确认且均具备参赛资格")
            if discipline == "mixed" and {
                p.get("gender"),
                players[partner].get("gender"),
            } != {"male", "female"}:
                raise ValueError("混双固定搭档必须一男一女")
            if u in remaining:
                fixed.append([u, partner])
                remaining.pop(u)
                remaining.pop(partner)
    ids = list(remaining)
    rng.shuffle(ids)
    if discipline == "mixed":
        males = [u for u in ids if players[u].get("gender") == "male"]
        females = [u for u in ids if players[u].get("gender") == "female"]
        if len(males) != len(females) or len(males) + len(females) != len(ids):
            raise ValueError("混双男女名额不足或性别未填写")
        return fixed + [list(x) for x in zip(males, females)]
    if len(ids) % 2:
        raise ValueError("双打尚有未配对人员")
    return fixed + [ids[i : i + 2] for i in range(0, len(ids), 2)]


def schedule(matches, config, start):
    by_key = {m["key"]: m for m in matches}
    courts = (
        config.courts[: config.max_parallel] if config.max_parallel else config.courts
    )
    availability = {c: start for c in courts}
    round_ends = defaultdict(dict)
    duration = timedelta(minutes=config.match_minutes)
    ordered = sorted(
        matches, key=lambda m: (m["round_no"], m["group_no"], m["position"])
    )
    for m in ordered:
        if m.get("status") == "bye":
            continue
        ready = start
        for side in ("a", "b"):
            parent = by_key.get(m.get(f"source_{side}"))
            if parent and parent.get("scheduled_end"):
                ready = max(ready, parent["scheduled_end"])
        # A barrier per group/round prevents overlapping participant appearances
        # without scanning every prior match for large round-robin draws.
        ready = max(
            ready,
            max(
                (
                    end
                    for r, end in round_ends[m["group_no"]].items()
                    if r < m["round_no"]
                ),
                default=start,
            ),
        )
        court = min(courts, key=lambda c: max(availability[c], ready))
        m["court"] = court
        m["scheduled_at"] = max(availability[court], ready)
        m["scheduled_end"] = m["scheduled_at"] + duration
        availability[court] = m["scheduled_end"]
        ends = round_ends[m["group_no"]]
        ends[m["round_no"]] = max(ends.get(m["round_no"], start), m["scheduled_end"])
    return matches


def qualified_draw(qualifiers, origins, seed, third_place):
    """Backtracking first-round matching avoids same-group opponents whenever possible."""
    rng = random.Random(seed)
    ids = list(qualifiers)
    rng.shuffle(ids)
    size = 1 << (len(ids) - 1).bit_length()
    byes = size - len(ids)
    bye_teams, contested = ids[:byes], ids[byes:]
    budget = [10000]

    def pair(pool):
        budget[0] -= 1
        if budget[0] < 0:
            return None
        if not pool:
            return []
        a = pool[0]
        for b in pool[1:]:
            if origins[a] == origins[b]:
                continue
            tail = pair([v for v in pool[1:] if v != b])
            if tail is not None:
                return [(a, b), *tail]
        return None

    pairs = pair(contested)
    if pairs is None:
        pairs = list(zip(contested[::2], contested[1::2]))
    # knockout() fills first side of each pair, then second; preserve these paired positions.
    first = [a for a, b in pairs] + bye_teams
    second = [b for a, b in pairs]
    return knockout(first + second, 1, third_place)


def pair_grouped(players, config, seed, max_people):
    """Honor chosen groups, filling pairing gaps from consenting random entrants."""
    rng = random.Random(seed)
    players = [dict(p) for p in players]
    auto = [p for p in players if not p.get("requested_group")]
    rng.shuffle(auto)
    size = 1 if config.discipline == "singles" else 2
    total = max_people // size
    capacities = {
        g: total // config.group_count + int(g <= total % config.group_count)
        for g in range(1, config.group_count + 1)
    }
    groups = {g: [] for g in capacities}
    for g in groups:
        selected = [p for p in players if p.get("requested_group") == g]
        # A selected group must form complete teams; fill only random preferences.
        need = []
        if config.discipline == "mixed":
            male = sum(p.get("gender") == "male" for p in selected)
            female = sum(p.get("gender") == "female" for p in selected)
            need = ["female"] * max(0, male - female) + ["male"] * max(0, female - male)
        elif config.discipline == "doubles" and len(selected) % 2:
            need = [None]
        for gender in need:
            candidate = next(
                (
                    p
                    for p in auto
                    if p.get("pairing") != "fixed"
                    and (gender is None or p.get("gender") == gender)
                ),
                None,
            )
            if candidate is None:
                raise ValueError(f"第 {g} 组尚有未配对人员，请调整报名分组或搭档")
            auto.remove(candidate)
            selected.append(candidate)
        if selected:
            groups[g] = pair_players(selected, config.discipline, seed + str(g))
            if len(groups[g]) > capacities[g]:
                raise ValueError(f"第 {g} 组名额已满")
    if auto:
        for pair in pair_players(auto, config.discipline, seed):
            available = [g for g in groups if len(groups[g]) < capacities[g]]
            if not available:
                raise ValueError("分组名额已满")
            g = min(available, key=lambda g: len(groups[g]))
            groups[g].append(pair)
    if any(len(pairs) < 2 for pairs in groups.values()):
        raise ValueError("每组至少需要两队，请调整分组报名或补充参赛者")
    return [(g, pair) for g, pairs in groups.items() for pair in pairs]


def personal_position(teams, matches, user_id):
    team = next((t for t in teams if user_id in t.get("user_ids", [])), None)
    if not team:
        return None
    group = [m for m in matches if m["group_no"] == team["group_no"]]
    first = next(
        (
            m
            for m in group
            if m["round_no"] == 1
            and team["id"] in (m.get("team_a_id"), m.get("team_b_id"))
        ),
        None,
    )
    initial = [m for m in group if m["round_no"] == 1 and m["kind"] == "knockout"]
    half = (
        ("上半区" if first["position"] < len(initial) / 2 else "下半区")
        if first and len(initial) > 1
        else ("决赛签位" if initial else "循环组")
    )
    possible = set()
    path = []
    by_key = {m["key"]: m for m in group}
    for m in group:
        included = team["id"] in (m.get("team_a_id"), m.get("team_b_id"))
        for source in (m.get("source_a"), m.get("source_b")):
            parent = by_key.get(source)
            if source in possible and parent:
                if parent.get("status") in ("completed", "bye"):
                    included |= (
                        (parent.get("winner_id") != team["id"])
                        if m.get("source_outcome") == "loser"
                        else (parent.get("winner_id") == team["id"])
                    )
                else:
                    included = True
        if included:
            possible.add(m["key"])
            path.append(m)
    return {
        "team_id": team["id"],
        "group_no": team["group_no"],
        "half": half,
        "matches": path,
    }
