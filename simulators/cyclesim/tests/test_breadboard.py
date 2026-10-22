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


COMPACT = {"board_count": 5, "topology": "compact221", "grouping": "compact221"}


@pytest.mark.parametrize(
    "rotation,gap,margin", [(0, 0, 0), (90, 0, 0), (0, 0, 8), (90, 0, 8)]
)
def test_compact221_assignments_facing_ends_and_output_alignment(rotation, gap, margin):
    settings = COMPACT | {
        "orientation": str(rotation),
        "gap_mm": gap,
        "edge_rows": margin,
        "iterations": 80,
        "seed": 830 + margin,
    }
    result = search(settings)
    for candidate in result["candidates"]:
        boards = candidate["boards"]
        validate_boards(boards)
        p = {x["id"]: x for x in candidate["placements"]}
        for i in range(8):
            assert p[f"U_ALU_153_{i}"]["board"] == (0 if i < 4 else 1)
        for chip, board in [
            ("283_LO", 2),
            ("283_HI", 3),
            ("157_YBP_0", 4),
            ("157_YBP_1", 4),
        ]:
            assert p["U_ALU_" + chip]["board"] == board
        assert p["U_ALU_283_LO"]["row"] == 56 - margin
        assert p["U_ALU_283_HI"]["row"] == 1 + margin
        assert candidate["cluster"]["adder_body_gap_mm"] == pytest.approx(
            gap + 4.98 + 5.08 * margin
        )
        rects = dict(
            zip((x["id"] for x in candidate["placements"]), candidate["chip_rects"])
        )
        axis = 1 if rotation == 0 else 0
        centers = {chip: (r[axis] + r[axis + 2]) / 2 for chip, r in rects.items()}
        for a, y in [("283_LO", "157_YBP_0"), ("283_HI", "157_YBP_1")]:
            # The closest symmetric pair also reserves two free rows. At zero
            # margin this puts centers 1.32 mm away from the adder centers.
            assert abs(centers["U_ALU_" + a] - centers["U_ALU_" + y]) <= 1.32 + 1e-6
        assert (centers["U_ALU_283_LO"] + centers["U_ALU_283_HI"]) / 2 == pytest.approx(
            (centers["U_ALU_157_YBP_0"] + centers["U_ALU_157_YBP_1"]) / 2
        )
        assert len(candidate["contacts"]) == 192 and len(candidate["wires"]) == 90
        assert not candidate["routing_diagnostics"]
        for wire in candidate["wires"]:
            assert all(
                segment_clear(a, b, candidate["chip_rects"])
                for a, b in zip(wire["path"], wire["path"][1:])
            )


@pytest.mark.parametrize("change", [{"board": 3}, {"row": 28}])
def test_compact221_evaluate_rejects_board_change_or_central_drift(change):
    result = search(COMPACT | {"iterations": 40})
    candidate = deepcopy(result["candidates"][0])
    next(p for p in candidate["placements"] if p["id"] == "U_ALU_283_LO").update(change)
    with pytest.raises(ValueError):
        evaluate(
            {
                "settings": result["settings"],
                "boards": candidate["boards"],
                "placements": candidate["placements"],
            }
        )


@pytest.mark.parametrize(
    "change",
    [
        {"board_count": 4},
        {"edge_rows": -1},
        {"edge_rows": 9},
        {"edge_rows": True},
        {"grouping": "free"},
    ],
)
def test_compact221_rejects_invalid_contract(change):
    with pytest.raises(ValueError):
        search(COMPACT | change)


def test_compact221_lock_and_json_roundtrip():
    result = search(COMPACT | {"iterations": 80})
    candidate = result["candidates"][0]
    lock = next(p for p in candidate["placements"] if p["id"] == "U_ALU_283_LO")
    result = search(result["settings"] | {"locks": [lock]})
    assert all(
        next(p for p in c["placements"] if p["id"] == lock["id"]) == lock
        for c in result["candidates"]
    )
    candidate = result["candidates"][0]
    loaded = json.loads(
        json.dumps(
            {
                "settings": result["settings"],
                "boards": candidate["boards"],
                "placements": candidate["placements"],
            }
        )
    )
    assert evaluate(loaded)["id"] == candidate["id"]
    with pytest.raises(ValueError):
        search(result["settings"] | {"edge_rows": 1})


def test_compact221_shifted_input_lock_repositions_neighbours():
    lock = {"id": "U_ALU_153_1", "board": 0, "row": 34, "rotation": 180}
    result = search(COMPACT | {"iterations": 80, "locks": [lock]})
    for c in result["candidates"]:
        assert next(p for p in c["placements"] if p["id"] == lock["id"]) == lock


@pytest.mark.parametrize("gap", [-1, 0.01, 6, 50])
def test_nonzero_board_gap_is_rejected_in_every_mode(gap):
    for settings in ({}, COMPACT):
        with pytest.raises(ValueError):
            search(settings | {"gap_mm": gap})


@pytest.mark.parametrize("dx,dy", [(55.1, 0), (55, 165)])
def test_disconnected_or_corner_only_boards_are_rejected(dx, dy):
    boards = [
        {"id": 0, "x": 0, "y": 0, "rotation": 0},
        {"id": 1, "x": dx, "y": dy, "rotation": 0},
    ]
    with pytest.raises(ValueError, match="0 mm"):
        config({"board_count": 2, "topology": "custom", "custom_boards": boards})


def test_connected_staggered_custom_layout_and_disconnected_import():
    result = search(COMPACT | {"orientation": "0", "iterations": 40})
    c = result["candidates"][0]
    assert [(b["x"], b["y"]) for b in c["boards"]] == [
        (0, 0),
        (0, 165),
        (55, 0),
        (55, 165),
        (110, 82.5),
    ]
    payload = {
        "settings": result["settings"],
        "boards": deepcopy(c["boards"]),
        "placements": c["placements"],
    }
    # Sliding B5 along the contacting side is permitted.
    payload["boards"][4]["y"] += 10
    evaluate(payload)
    payload["boards"][4]["x"] += 0.01
    with pytest.raises(ValueError, match="0 mm"):
        evaluate(payload)


def test_separate_touching_pairs_do_not_form_a_joined_array():
    boards = [
        {"id": i, "x": x, "y": 0, "rotation": 0}
        for i, x in enumerate([0, 55, 200, 255])
    ]
    with pytest.raises(ValueError, match="0 mm"):
        validate_boards(boards)


def test_zigzag_skips_detached_orientation_without_clamping_offset():
    c = config({"topology": "zigzag", "orientation": "auto", "stagger_mm": 55})
    layouts = arrays(c)
    assert len(layouts) == 1 and layouts[0][1][0]["rotation"] == 0
    assert layouts[0][1][1]["y"] == 55
    with pytest.raises(ValueError, match="맞닿"):
        arrays(config({"topology": "zigzag", "orientation": "90", "stagger_mm": 55}))


@pytest.mark.parametrize(
    "row_gap,expected", [(1, (24, 33)), (2, (23, 34)), (3, (23, 34)), (4, (22, 35))]
)
def test_joined_boards_keep_reserved_output_rows(row_gap, expected):
    result = search(COMPACT | {"row_gap": row_gap, "iterations": 40})
    for c in result["candidates"]:
        rows = tuple(p["row"] for p in c["placements"] if "157" in p["id"])
        assert rows == expected
        assert rows[1] - rows[0] - 8 >= row_gap
