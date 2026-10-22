"""Independent checks of breadboard electrical strips, placement and routing bounds."""

from copy import deepcopy
import json
import math

import pytest

from simulators.cyclesim.breadboard import (
    PROFILE,
    arrays,
    config,
    contacts,
    evaluate,
    hole,
    initial,
    point,
    search,
    segment_clear,
    validate_boards,
    validate_placements,
)


def test_generic_board_hole_count_pitch_and_dip_contacts():
    assert (
        PROFILE["rows"] * len(PROFILE["columns"]) + len(PROFILE["rail_y_mm"]) * 4 == 830
    )
    c = config({"topology": "horizontal", "orientation": "0"})
    boards = arrays(c)[0][1]
    placements = initial(c, 0)
    pins, _ = contacts(placements, boards)
    assert len(pins) == 192
    a, b = pins[("U_ALU_153_0", "1G")], pins[("U_ALU_153_0", "VCC")]
    assert a["column"] == "e" and b["column"] == "f" and a["row"] == b["row"]
    assert b["xy"][0] - a["xy"][0] == pytest.approx(7.62)
    assert a["strip"] != b["strip"]
    assert pins[("U_ALU_153_0", "B")]["xy"][1] - a["xy"][1] == pytest.approx(2.54)
    placements[0]["rotation"] = 180
    turned, _ = contacts(placements, boards)
    assert turned[("U_ALU_153_0", "1G")]["column"] == "f"
    assert turned[("U_ALU_153_0", "1G")]["row"] == a["row"] + 7


@pytest.mark.parametrize(
    "rotation,expected",
    [(0, [10, 20]), (90, [145, 10]), (180, [45, 145]), (270, [20, 45])],
)
def test_board_rotations_use_bounding_box_origin(rotation, expected):
    assert point({"x": 0, "y": 0, "rotation": rotation}, 10, 20) == expected


@pytest.mark.parametrize("topology", ["horizontal", "vertical", "grid", "zigzag"])
def test_array_has_no_overlapping_boards(topology):
    for _, boards in arrays(
        config({"board_count": 8, "topology": topology, "gap_mm": 0})
    ):
        validate_boards(boards)


def test_search_is_repeatable_and_keeps_stage_order():
    a, b = search({"iterations": 80}), search({"iterations": 80})
    assert [c["id"] for c in a["candidates"]] == [c["id"] for c in b["candidates"]]
    assert {c["topology"] for c in a["candidates"]} == {
        "horizontal",
        "vertical",
        "grid",
        "zigzag",
    }
    assert a["statistics"]["evaluated"] <= 96
    for c in a["candidates"]:
        validate_placements(c["placements"], c["boards"], 2, "stages")
        assert len(c["placements"]) == 12
        assert c["routing_diagnostics"] == []


def test_routes_use_distinct_free_holes_in_same_strip_and_avoid_bodies():
    result = search({"topology": "zigzag", "orientation": "0", "iterations": 80})
    for c in result["candidates"]:
        pin_holes = {(p["board"], p["row"], p["column"]) for p in c["contacts"]}
        used = set()
        expected_length = 0
        for w in c["wires"]:
            for end in [w["from"], w["to"]]:
                key = (end["board"], end["row"], end["column"])
                assert key not in pin_holes and key not in used
                used.add(key)
                pin = next(
                    p
                    for p in c["contacts"]
                    if p["component"] == end["component"] and p["pin"] == end["pin"]
                )
                assert (
                    pin["row"] == end["row"]
                    and pin["board"] == end["board"]
                    and pin["net"] == w["net"]
                )
                assert (pin["column"] in "abcde") == (end["column"] in "abcde")
                assert end["xy"] == hole(
                    c["boards"][end["board"]], end["row"], end["column"]
                )
            assert w["path"][0] == w["from"]["xy"] and w["path"][-1] == w["to"]["xy"]
            length = 0
            for a, b in zip(w["path"], w["path"][1:]):
                assert a[0] == b[0] or a[1] == b[1]
                assert segment_clear(a, b, c["chip_rects"])
                length += abs(a[0] - b[0]) + abs(a[1] - b[1])
            assert w["length_mm"] == pytest.approx(length, abs=0.011)
            expected_length += w["length_mm"]
        assert c["routed_mm"] == pytest.approx(expected_length, abs=0.011)
        assert len(c["wires"]) == 90


def test_locks_survive_search_and_evaluate_rejects_moving_one():
    base = search({"iterations": 40})["candidates"][0]
    lock = base["placements"][0]
    settings = {"iterations": 80, "locks": [lock]}
    r = search(settings)
    for c in r["candidates"]:
        assert next(p for p in c["placements"] if p["id"] == lock["id"]) == lock
    c = deepcopy(r["candidates"][0])
    c["placements"][0]["rotation"] = 180 - lock["rotation"]
    with pytest.raises(ValueError, match="고정"):
        evaluate(
            {"settings": settings, "boards": c["boards"], "placements": c["placements"]}
        )


def test_custom_layout_roundtrip_and_reject_overlap():
    r = search({"iterations": 40})
    c = r["candidates"][0]
    settings = r["settings"] | {"topology": "custom", "custom_boards": c["boards"]}
    loaded = json.loads(
        json.dumps(
            {"settings": settings, "boards": c["boards"], "placements": c["placements"]}
        )
    )
    validated = evaluate(loaded)
    assert validated["id"] == c["id"] and validated["wires"] == c["wires"]
    loaded["boards"][1].update(loaded["boards"][0] | {"id": 1})
    with pytest.raises(ValueError, match="겹"):
        evaluate(loaded)


@pytest.mark.parametrize(
    "bad",
    [
        {"board_count": True},
        {"iterations": 1601},
        {"gap_mm": math.nan},
        {"gap_mm": math.inf},
        {"locks": [{"id": [], "board": 0, "row": 1, "rotation": 0}]},
        {"custom_boards": {}},
        {"grouping": "unknown"},
    ],
)
def test_bad_requests_fail_before_search(bad):
    with pytest.raises(ValueError):
        search(bad)


def test_capacity_failure_is_bounded_and_explicit():
    with pytest.raises(ValueError, match="初|초기"):
        search({"board_count": 2, "row_gap": 4})


def test_two_boards_and_nibble_grouping_are_supported():
    r = search({"board_count": 2, "grouping": "nibbles", "iterations": 40})
    for c in r["candidates"]:
        validate_placements(c["placements"], c["boards"], 2, "nibbles")
        assert not c["routing_diagnostics"]


def test_eight_board_initial_stage_layout_uses_every_board():
    c = config({"board_count": 8})
    placements = initial(c, 0)
    assert {p["board"] for p in placements} == set(range(8))
    validate_placements(placements, arrays(c)[0][1], 2, "stages")
