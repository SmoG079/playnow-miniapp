"""Validate a complete seat permutation without changing team membership."""
from collections import Counter
from app.services import tournament_engine as engine


def played(matches):
    return any(m.get("status") == "completed" or m.get("score") or m.get("walkover") or m.get("is_draw") or (m.get("winner_id") and m.get("status") != "bye") for m in matches)


def seats(teams, matches, snapshot):
    if snapshot.get("positions") is not None:
        return snapshot["positions"]
    if any(m["kind"] == "knockout" for m in matches):
        return [dict(group_no=m["group_no"], position=2*m["position"]+side, team_id=m.get(f"team_{letter}_id"))
                for m in matches if m["kind"] == "knockout" and m["round_no"] == 1
                for side, letter in enumerate(("a", "b"))]
    result = []
    for group in sorted({t["group_no"] for t in teams}):
        members = [t["id"] for t in teams if t["group_no"] == group]
        size = len(members) + len(members) % 2
        ordered = [None] * size
        for m in matches:
            if m["group_no"] == group and m["round_no"] == 1:
                ordered[m["position"]] = m["team_a_id"]
                ordered[size - 1 - m["position"]] = m["team_b_id"]
        missing = [ident for ident in members if ident not in ordered]
        if missing:
            ordered[0] = missing[0]  # Odd roster: first player meets the virtual bye.
        for position, ident in enumerate(i for i in ordered if i is not None):
            result.append(dict(group_no=group, position=position, team_id=ident))
    return result


def validate_positions(original, proposed, knockout):
    key = lambda s:(s["group_no"], s["position"])
    if len(proposed) != len(original) or len({key(s) for s in proposed}) != len(proposed) or {key(s) for s in proposed} != {key(s) for s in original}:
        raise ValueError("须提交完整且不重复的签位")
    if Counter(s["team_id"] for s in proposed) != Counter(s["team_id"] for s in original):
        raise ValueError("参赛单位不能重复、遗漏或替换")
    counts = lambda rows:Counter(s["group_no"] for s in rows if s["team_id"] is not None)
    if counts(original) != counts(proposed):
        raise ValueError("跨组交换必须保持每组参赛数量")
    if knockout:
        by_key={key(s):s["team_id"] for s in proposed}
        for group, position in by_key:
            if position % 2 == 0 and by_key[(group,position)] is None and by_key[(group,position+1)] is None:
                raise ValueError("首轮对阵不能双方均轮空")
    return sorted(proposed, key=key)


def rebuild(matches, positions, mapping, knockout):
    if not knockout:
        result=[]
        for group in sorted({s["group_no"] for s in positions}):
            result += engine.round_robin([mapping[s["team_id"]] for s in positions if s["group_no"]==group], group)
        return result
    slots={(s["group_no"],s["position"]):mapping.get(s["team_id"]) for s in positions}
    result=[]
    for m in matches:
        row={k:m[k] for k in ("key","group_no","round_no","position","kind","source_a","source_b","source_outcome") if k in m}
        row.update(team_a_id=None,team_b_id=None,status="pending",winner_id=None)
        if row["kind"] == "knockout" and row["round_no"]==1:
            row.update(team_a_id=slots[(m["group_no"],2*m["position"])],team_b_id=slots[(m["group_no"],2*m["position"]+1)])
        result.append(row)
    return engine.resolve(result)
