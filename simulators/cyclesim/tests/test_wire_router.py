"""Independent geometric and electrical checks for individual physical jumpers."""

from itertools import combinations, pairwise

import pytest

from simulators.cyclesim import breadboard as bb
from simulators.cyclesim.wire_router import Router, audit, intersection


def on_segment(p, a, b):
    area = (p[0] - a[0]) * (b[1] - a[1]) - (p[1] - a[1]) * (b[0] - a[0])
    return abs(area) < 1e-6 and all(
        min(a[k], b[k]) - 1e-6 <= p[k] <= max(a[k], b[k]) + 1e-6 for k in (0, 1)
    )


def check_separate_jumpers(detail):
    wires = detail["wires"]
    assert not detail["routing_diagnostics"]
    assert len(wires) == 90
    assert {w["id"] for w in wires} == {f"J{i:03d}" for i in range(1, 91)}
    assert detail["overlap_count"] == detail["unintended_contacts"] == 0
    terminals = {tuple(p["xy"]) for p in detail["contacts"]}
    terminals.update(tuple(w[e]["xy"]) for w in wires for e in ("from", "to"))
    for w in wires:
        own = {tuple(w["from"]["xy"]), tuple(w["to"]["xy"])}
        for a, b in zip(w["path"], w["path"][1:]):
            assert all(not on_segment(t, a, b) for t in terminals - own)
    actual_crossings = set()
    for w, v in combinations(wires, 2):
        for a, b in zip(w["path"], w["path"][1:]):
            for c, d in zip(v["path"], v["path"][1:]):
                # No wire endpoint or bend may touch any other wire, including
                # another jumper belonging to the same electrical net.
                assert not any(
                    (
                        on_segment(a, c, d),
                        on_segment(b, c, d),
                        on_segment(c, a, b),
                        on_segment(d, a, b),
                    )
                )
                if (a[0] == b[0]) != (c[0] == d[0]):
                    xy = (a[0], c[1]) if a[0] == b[0] else (c[0], a[1])
                    if on_segment(xy, a, b) and on_segment(xy, c, d):
                        actual_crossings.add((w["id"], v["id"], xy))
    recorded = {
        (c["under"], c["over"], tuple(c["xy"])) for c in detail["crossing_points"]
    }
    assert actual_crossings == recorded
    assert len(recorded) == detail["crossings"]
    # Check the physical jumper graph connects every modeled pin of each net.
    pins = {(p["component"], p["pin"]): p for p in detail["contacts"]}
    for net, ends in bb.nets_to_route(pins):
        remaining = {p["strip"] for p in ends}
        reached = {remaining.pop()}
        edges = [w for w in wires if w["net"] == net["id"]]
        for _ in range(len(ends)):
            for w in edges:
                pair = {w["from"]["strip"], w["to"]["strip"]}
                if pair & reached:
                    reached.update(pair)
        assert remaining <= reached


def test_compact_routes_have_no_hidden_junctions_and_keep_net_connectivity():
    c = bb.config(
        {
            "topology": "compact221",
            "grouping": "compact221",
            "board_count": 5,
            "orientation": "0",
        }
    )
    boards = bb.arrays(c)[0][1]
    check_separate_jumpers(bb.detailed(bb.initial(c, 0), boards))


def test_three_way_branch_uses_three_distinct_holes_in_one_strip(monkeypatch):
    original = bb.mst

    def branched(ends):
        if ends[0]["net"] != "net_bctrl0":
            return original(ends)
        return [(ends[0], p, 0) for p in ends[1:4]] + [
            (ends[i - 1], ends[i], 0) for i in range(4, len(ends))
        ]

    monkeypatch.setattr(bb, "mst", branched)
    c = bb.config(
        {
            "topology": "compact221",
            "grouping": "compact221",
            "board_count": 5,
            "orientation": "0",
        }
    )
    detail = bb.detailed(bb.initial(c, 0), bb.arrays(c)[0][1])
    branch = sorted(
        (w for w in detail["wires"] if w["net"] == "net_bctrl0"), key=lambda w: w["id"]
    )[:3]
    assert len({w["from"]["strip"] for w in branch}) == 1
    assert len({w["from"]["hole"] for w in branch}) == 3
    assert len({tuple(w["path"][0]) for w in branch}) == 3
    check_separate_jumpers(detail)


@pytest.mark.parametrize(
    "other,kind",
    [
        (((5, -2), (5, 2)), "cross"),
        (((5, 0), (5, 2)), "touch"),
        (((3, 0), (7, 0)), "overlap"),
        (((0, 2), (10, 2)), None),
    ],
)
def test_crossings_are_distinct_from_t_junctions_and_overlaps(other, kind):
    result = intersection((0, 0), (10, 0), *other)
    assert (result[0] if result else None) == kind


def test_same_net_crossing_is_reported_as_two_independent_wires():
    result = audit(
        [
            {"id": "J001", "net": "same", "path": [[0, 0], [10, 0]]},
            {"id": "J002", "net": "same", "path": [[5, -2], [5, 2]]},
        ]
    )
    assert result["crossing_points"] == [
        {"xy": [5, 0], "over": "J002", "under": "J001"}
    ]
    assert result["overlap_count"] == result["unintended_contacts"] == 0


def test_router_avoids_reserved_terminal_and_reports_bounded_failure():
    router = Router([], [[0, 0], [10, 0], [5, 0]])
    path, _ = router.route([0, 0], [10, 0])
    assert path is not None
    assert all(not on_segment((5, 0), a, b) for a, b in pairwise(path))
    assert router.grid_route([0, 0], [10, 0], budget=0) is None
    enclosed = Router([[-1, -1, 1, 1]], [[0, 0], [10, 0]])
    assert enclosed.route([0, 0], [10, 0]) == (None, None)
