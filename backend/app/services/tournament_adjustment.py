"""Validate a complete seat permutation without changing team membership."""
from collections import Counter
from app.services import tournament_engine as engine


def played(matches):
    return any(m.get("status") == "completed" or m.get("score") or m.get("walkover") or m.get("is_draw") or (m.get("winner_id") and m.get("status") != "bye") for m in matches)


def initial_positions(groups, matches):
    if any(m["kind"] == "knockout" for m in matches):
        return [dict(group_no=m["group_no"], position=2*m["position"]+side, team_id=m.get(f"team_{letter}_id"))
                for m in matches if m["kind"] == "knockout" and m["round_no"] == 1
                for side, letter in enumerate(("a", "b"))]
    return [dict(group_no=group, position=position, team_id=ident)
            for group, members in enumerate(groups, 1) for position, ident in enumerate(members)]


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
