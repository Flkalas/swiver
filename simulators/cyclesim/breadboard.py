"""Generic 830 geometry and bounded ALU placement search.

Engineering convention, not a particular vendor's mechanical drawing. Electrical
connectivity always comes from circuit_definition; this module never evaluates ALU
signals. Lengths are planar rectilinear estimates, without wire rise/slack.
"""

from __future__ import annotations

from copy import deepcopy
from functools import lru_cache
import hashlib
import json
import math
import random
import time

from simulators.cyclesim.viewer_model import circuit_definition

VERSION = "bb830-search-v1"
PITCH = 2.54
PROFILE = {
    "id": "generic-830-v1",
    "width_mm": 55.0,
    "height_mm": 165.0,
    "pitch_mm": PITCH,
    "rows": 63,
    "terminal_holes": 630,
    "rail_holes": 200,
    "row_origin_mm": 3.76,
    "columns": dict(
        zip(
            "abcdefghij",
            [13.53 + i * PITCH for i in range(5)]
            + [31.31 + i * PITCH for i in range(5)],
        )
    ),
    "rail_x_mm": [3.5, 6.04, 48.96, 51.5],
    "rail_y_mm": [round(8.84 + (i + i // 5) * PITCH, 2) for i in range(50)],
    "notes": [
        "범용 830 가정: 55 × 165 mm, 63행, 2.54 mm 격자. 제조사 실측 도면 아님.",
        "결합 돌기는 제외. 같은 행 a–e / f–j는 각각 연결, 중앙 홈 양쪽은 분리.",
        "전원 레일 중간 단절은 설정에 표시하며 신호 배선 비용에는 포함하지 않음.",
    ],
}
TOPOLOGIES = ("horizontal", "vertical", "grid", "zigzag")
LABELS = {
    "horizontal": "가로 배열",
    "vertical": "세로 배열",
    "grid": "격자 배열",
    "zigzag": "지그재그",
    "custom": "직접 지정",
}
LIMITATIONS = [
    "유한 후보 탐색 결과이며 전역 최적해 보장이 아닙니다.",
    "평면 경로 길이 추정입니다. 점퍼 높이·여유 길이·선 두께·타이밍은 계산하지 않습니다.",
    "칩 간 신호·제어 넷만 평가합니다. 전원·GND·Enable 타이, 레일 간 점퍼, 외부 입출력 배선은 별도입니다.",
    "경로의 교차는 도통을 뜻하지 않습니다. 교차부 높이와 디커플링 실장은 별도 확인해야 합니다.",
]


@lru_cache(maxsize=1)
def definition():
    return circuit_definition()


def number(value, name, lo, hi, integer=False):
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
    ):
        raise ValueError(f"{name}: 숫자가 필요합니다.")
    if not lo <= value <= hi or (integer and int(value) != value):
        raise ValueError(f"{name}: {lo}–{hi} 범위를 확인하세요.")
    return int(value) if integer else float(value)


def config(raw):
    if not isinstance(raw, dict):
        raise ValueError("탐색 설정은 객체여야 합니다.")
    known = {
        "board_count",
        "topology",
        "gap_mm",
        "stagger_mm",
        "orientation",
        "row_gap",
        "iterations",
        "seed",
        "priority",
        "grouping",
        "rail_split",
        "locks",
        "custom_boards",
    }
    if set(raw) - known:
        raise ValueError("알 수 없는 탐색 설정: " + ", ".join(sorted(set(raw) - known)))
    c = {
        "board_count": 4,
        "topology": "all",
        "gap_mm": 6,
        "stagger_mm": 55,
        "orientation": "auto",
        "row_gap": 2,
        "iterations": 400,
        "seed": 830,
        "priority": "balanced",
        "grouping": "stages",
        "rail_split": True,
        "locks": [],
        "custom_boards": [],
    } | deepcopy(raw)
    for key, lo, hi in (
        ("board_count", 2, 8),
        ("row_gap", 1, 4),
        ("iterations", 40, 1600),
        ("seed", 0, 2147483647),
    ):
        c[key] = number(c[key], key, lo, hi, True)
    for key, lo, hi in (("gap_mm", 0, 50), ("stagger_mm", 0, 165)):
        c[key] = number(c[key], key, lo, hi)
    if (
        c["topology"] not in (*TOPOLOGIES, "all", "custom")
        or c["priority"] not in ("short", "readable", "balanced")
        or c["orientation"] not in ("auto", "0", "90")
        or c["grouping"] not in ("stages", "nibbles", "free")
    ):
        raise ValueError("배열/방향/우선순위 설정을 확인하세요.")
    if type(c["rail_split"]) is not bool:
        raise ValueError("rail_split은 참/거짓이어야 합니다.")
    if not isinstance(c["locks"], list) or len(c["locks"]) > 12:
        raise ValueError("고정할 칩은 최대 12개입니다.")
    ids = {p["id"] for p in definition()["components"]}
    seen = set()
    for lock in c["locks"]:
        if (
            not isinstance(lock, dict)
            or set(lock) != {"id", "board", "row", "rotation"}
            or not isinstance(lock["id"], str)
            or lock["id"] not in ids
            or lock["id"] in seen
        ):
            raise ValueError("칩 고정 정보가 잘못되었거나 중복입니다.")
        seen.add(lock["id"])
        lock["board"] = number(lock["board"], "board", 0, c["board_count"] - 1, True)
        lock["row"] = number(lock["row"], "row", 1, 56, True)
        if type(lock["rotation"]) is not int or lock["rotation"] not in (0, 180):
            raise ValueError("칩 회전은 0 또는 180도입니다.")
    if not isinstance(c["custom_boards"], list):
        raise ValueError("custom_boards는 배열이어야 합니다.")
    if c["topology"] == "custom":
        if len(c["custom_boards"]) != c["board_count"]:
            raise ValueError("보드 수와 직접 지정 좌표 수가 다릅니다.")
        for i, b in enumerate(c["custom_boards"]):
            if (
                not isinstance(b, dict)
                or set(b) != {"id", "x", "y", "rotation"}
                or type(b["id"]) is not int
                or b["id"] != i
            ):
                raise ValueError("보드 좌표는 id 순서로 지정하세요.")
            number(b["x"], "보드 X", -2000, 2000)
            number(b["y"], "보드 Y", -2000, 2000)
            if type(b["rotation"]) is not int or b["rotation"] not in (0, 90, 180, 270):
                raise ValueError("보드 회전은 0/90/180/270도입니다.")
        validate_boards(c["custom_boards"])
    return c


def point(board, x, y):
    """Board x/y is its rotated bounding box's upper-left, not its pivot."""
    r = board["rotation"]
    if r == 90:
        x, y = 165 - y, x
    elif r == 180:
        x, y = 55 - x, 165 - y
    elif r == 270:
        x, y = y, 55 - x
    return [round(board["x"] + x, 3), round(board["y"] + y, 3)]


def board_rect(b):
    w, h = (55, 165) if b["rotation"] % 180 == 0 else (165, 55)
    return [b["x"], b["y"], b["x"] + w, b["y"] + h]


def overlap(a, b):
    return (
        a[0] < b[2] - 1e-6
        and b[0] < a[2] - 1e-6
        and a[1] < b[3] - 1e-6
        and b[1] < a[3] - 1e-6
    )


def validate_boards(boards):
    for i, a in enumerate(boards):
        for b in boards[i + 1 :]:
            if overlap(board_rect(a), board_rect(b)):
                raise ValueError(f"보드 B{a['id'] + 1}와 B{b['id'] + 1}가 겹칩니다.")


def arrays(c):
    if c["topology"] == "custom":
        return [("custom", deepcopy(c["custom_boards"]))]
    layouts = []
    for topology in TOPOLOGIES if c["topology"] == "all" else [c["topology"]]:
        for rot in (0, 90) if c["orientation"] == "auto" else [int(c["orientation"])]:
            w, h = (55, 165) if rot == 0 else (165, 55)
            boards = []
            for i in range(c["board_count"]):
                if topology == "horizontal":
                    x, y = i * (w + c["gap_mm"]), 0
                elif topology == "vertical":
                    x, y = 0, i * (h + c["gap_mm"])
                elif topology == "grid":
                    x, y = (
                        (i % math.ceil(c["board_count"] / 2)) * (w + c["gap_mm"]),
                        (i // math.ceil(c["board_count"] / 2)) * (h + c["gap_mm"]),
                    )
                else:
                    x, y = i * (w + c["gap_mm"]), (i % 2) * c["stagger_mm"]
                boards.append({"id": i, "x": x, "y": y, "rotation": rot})
            layouts.append((topology, boards))
    return layouts


def validate_placements(placements, boards, gap, grouping="free"):
    if (
        len(placements) != 12
        or any(not isinstance(p["id"], str) for p in placements)
        or {p["id"] for p in placements}
        != {p["id"] for p in definition()["components"]}
    ):
        raise ValueError("12개 칩이 각각 한 번씩 배치되어야 합니다.")
    for i, p in enumerate(placements):
        if (
            type(p["board"]) is not int
            or not 0 <= p["board"] < len(boards)
            or type(p["row"]) is not int
            or not 1 <= p["row"] <= 56
            or type(p["rotation"]) is not int
            or p["rotation"] not in (0, 180)
        ):
            raise ValueError("칩 보드/행/방향이 올바르지 않습니다.")
        for q in placements[i + 1 :]:
            if p["board"] == q["board"] and abs(p["row"] - q["row"]) < 8 + gap:
                raise ValueError("칩 몸체/핀 또는 예약한 행 간격이 겹칩니다.")
    ordered = sorted(placements, key=lambda p: (p["board"], p["row"]))
    if grouping == "stages":
        stages = [
            0 if "153" in p["id"] else 1 if "283" in p["id"] else 2 for p in ordered
        ]
        if stages != sorted(stages):
            raise ValueError("8–2–2 단계 순서(보드 번호·행 순서)를 벗어납니다.")
    elif grouping == "nibbles":
        ids = [p["id"] for p in definition()["components"]]
        if [p["id"] for p in ordered] != [
            ids[i] for i in (0, 1, 2, 3, 8, 10, 4, 5, 6, 7, 9, 11)
        ]:
            raise ValueError("하위/상위 4비트 묶음 순서를 벗어납니다.")


def hole(board, row, column):
    return point(
        board, PROFILE["columns"][column], PROFILE["row_origin_mm"] + (row - 1) * PITCH
    )


def contacts(placements, boards):
    components = {p["id"]: p for p in definition()["components"]}
    result = {}
    rects = []
    for p in placements:
        comp = components[p["id"]]
        for pin, meta in comp["package"]["pins"].items():
            n = meta["number"]
            left = n <= 8
            offset = n - 1 if left else 16 - n
            if p["rotation"] == 180:
                left, offset = not left, 7 - offset
            row = p["row"] + offset
            col = "e" if left else "f"
            result[(p["id"], pin)] = {
                "component": p["id"],
                "pin": pin,
                "number": n,
                "net": comp["pins"][pin],
                "board": p["board"],
                "row": row,
                "column": col,
                "xy": hole(boards[p["board"]], row, col),
                "strip": f"B{p['board'] + 1}:{row}:{'ae' if left else 'fj'}",
            }
        y = PROFILE["row_origin_mm"] + (p["row"] - 1) * PITCH
        corners = [
            point(boards[p["board"]], x, yy)
            for x in (24.325, 30.675)
            for yy in (y - 1.27, y + 19.05)
        ]
        rects.append(
            [
                min(x for x, y in corners),
                min(y for x, y in corners),
                max(x for x, y in corners),
                max(y for x, y in corners),
            ]
        )
    return result, rects


def manhattan(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def mst(ends):
    """Deterministic Prim on rectilinear pin distances, not a routed optimum."""
    if len(ends) < 2:
        return []
    attached = {0}
    edges = []
    best = {
        j: (manhattan(ends[0]["xy"], ends[j]["xy"]), 0) for j in range(1, len(ends))
    }
    while best:
        j, (distance, i) = min(
            best.items(), key=lambda item: (item[1][0], item[1][1], item[0])
        )
        edges.append((ends[i], ends[j], distance))
        del best[j]
        attached.add(j)
        for k in best:
            d = manhattan(ends[j]["xy"], ends[k]["xy"])
            if d < best[k][0]:
                best[k] = (d, j)
    return edges


def nets_to_route(pins):
    for net in definition()["nets"]:
        if net["kind"] != "power" and len(net["endpoints"]) >= 2:
            yield net, [pins[(e["component"], e["pin"])] for e in net["endpoints"]]


def readability(placements):
    """Explicit penalty: inversions within 153 order, stage mixing, opposite notches."""
    loc = {p["id"]: (p["board"], p["row"]) for p in placements}
    bits = [loc[f"U_ALU_153_{i}"] for i in range(8)]
    inversions = sum(bits[i] > bits[j] for i in range(8) for j in range(i + 1, 8))
    mixed = sum(
        max(0, len({p["id"].split("_")[2] for p in placements if p["board"] == b}) - 1)
        for b in {p["board"] for p in placements}
    )
    flips = sum(p["rotation"] == 180 for p in placements)
    return inversions * 3 + mixed * 2 + flips


def estimate(placements, boards):
    pins, _ = contacts(placements, boards)
    length = 0.0
    longest = 0.0
    cross_board = 0
    for _, ends in nets_to_route(pins):
        for a, b, d in mst(ends):
            length += d
            longest = max(longest, d)
            cross_board += a["board"] != b["board"]
    return {
        "estimated_mm": round(length, 2),
        "longest_estimated_mm": round(longest, 2),
        "interboard": cross_board,
        "readability_penalty": readability(placements),
    }


def score(metrics, priority):
    reading = {"short": 2, "balanced": 35, "readable": 180}[priority]
    interboard = {"short": 0, "balanced": 12, "readable": 35}[priority]
    return round(
        metrics["estimated_mm"]
        + metrics["readability_penalty"] * reading
        + metrics["interboard"] * interboard,
        2,
    )


def initial(c, variant):
    ids = [p["id"] for p in definition()["components"]]
    count = c["board_count"]
    step = 8 + c["row_gap"]
    capacity = (63 + c["row_gap"]) // step
    locks = {p["id"]: deepcopy(p) for p in c["locks"]}
    if count * capacity < 12:
        raise ValueError("현재 행 간격에서는 보드가 부족합니다.")
    validate_partial = list(locks.values())
    for i, p in enumerate(validate_partial):
        for q in validate_partial[i + 1 :]:
            if p["board"] == q["board"] and abs(p["row"] - q["row"]) < step:
                raise ValueError(
                    "고정한 칩끼리 겹칩니다. 고정을 해제하거나 행을 바꾸세요."
                )
    order = (
        list(range(12)) if variant % 2 == 0 else [0, 1, 2, 3, 8, 10, 4, 5, 6, 7, 9, 11]
    )
    preferred = {}
    if variant % 2 == 0 and count >= 3:
        if count == 3:
            groups = [[0, 1, 2, 3], [4, 5, 6, 7], [8, 9, 10, 11]]
        else:
            groups = [[] for _ in range(count - 2)] + [[8, 9], [10, 11]]
            for i in range(8):
                groups[i * (count - 2) // 8].append(i)
        for b, indices in enumerate(groups):
            for i in indices:
                preferred[i] = b
    else:
        for j, i in enumerate(order):
            preferred[i] = j * count // 12
    out = list(locks.values())
    for i in order:
        if ids[i] in locks:
            continue
        preferred_board = preferred[i]
        added = False
        for b in [preferred_board] + [b for b in range(count) if b != preferred_board]:
            for row in range(3, 57):
                if all(p["board"] != b or abs(row - p["row"]) >= step for p in out):
                    out.append({"id": ids[i], "board": b, "row": row, "rotation": 0})
                    added = True
                    break
            if added:
                break
        if not added:
            raise ValueError("고정 위치와 행 간격 때문에 남은 칩을 배치할 수 없습니다.")
    return sorted(out, key=lambda p: ids.index(p["id"]))


def segment_clear(a, b, rects):
    for x0, y0, x1, y1 in rects:
        if (
            a[0] == b[0]
            and x0 < a[0] < x1
            and max(min(a[1], b[1]), y0) < min(max(a[1], b[1]), y1) - 1e-6
        ):
            return False
        if (
            a[1] == b[1]
            and y0 < a[1] < y1
            and max(min(a[0], b[0]), x0) < min(max(a[0], b[0]), x1) - 1e-6
        ):
            return False
    return True


def route(a, b, rects):
    candidates = [[a, [b[0], a[1]], b], [a, [a[0], b[1]], b]]
    for x in sorted(
        {round(r[i] + delta, 3) for r in rects for i, delta in ((0, -2.54), (2, 2.54))}
    ):
        candidates.append([a, [x, a[1]], [x, b[1]], b])
    for y in sorted(
        {round(r[i] + delta, 3) for r in rects for i, delta in ((1, -2.54), (3, 2.54))}
    ):
        candidates.append([a, [a[0], y], [b[0], y], b])
    best = None
    length = math.inf
    for path in candidates:
        d = sum(manhattan(x, y) for x, y in zip(path, path[1:]))
        if d >= length:
            continue
        if all(segment_clear(x, y, rects) for x, y in zip(path, path[1:])):
            best = [path[0]] + [v for u, v in zip(path, path[1:]) if v != u]
            length = d
    return best, round(length, 2) if best else None


def crossing_count(wires):
    count = 0
    for i, a in enumerate(wires):
        for b in wires[i + 1 :]:
            if a["net"] == b["net"]:
                continue
            for p, q in zip(a["path"], a["path"][1:]):
                for r, s in zip(b["path"], b["path"][1:]):
                    if (
                        p[1] == q[1]
                        and r[0] == s[0]
                        and min(p[0], q[0]) < r[0] < max(p[0], q[0])
                        and min(r[1], s[1]) < p[1] < max(r[1], s[1])
                    ):
                        count += 1
                    elif (
                        p[0] == q[0]
                        and r[1] == s[1]
                        and min(p[1], q[1]) < r[1] < max(p[1], q[1])
                        and min(r[0], s[0]) < p[0] < max(r[0], s[0])
                    ):
                        count += 1
    return count


def detailed(placements, boards):
    pins, rects = contacts(placements, boards)
    used = set()
    wires = []
    diagnostics = []

    def contact(pin):
        cols = "dcba" if pin["column"] == "e" else "ghij"
        for col in cols:
            key = (pin["board"], pin["row"], col)
            if key not in used:
                used.add(key)
                return dict(
                    pin,
                    column=col,
                    xy=hole(boards[pin["board"]], pin["row"], col),
                    hole=f"B{pin['board'] + 1}:{col}{pin['row']}",
                )
        return None

    for net, ends in nets_to_route(pins):
        for a, b, _ in mst(ends):
            aa, bb = contact(a), contact(b)
            if aa is None or bb is None:
                diagnostics.append(f"{net['id']}: 점퍼용 접점 부족")
                continue
            path, length = route(aa["xy"], bb["xy"], rects)
            if path is None:
                diagnostics.append(f"{net['id']}: 칩 몸체를 피하는 경로 미발견")
                continue
            wires.append(
                {
                    "net": net["id"],
                    "kind": net["kind"],
                    "from": aa,
                    "to": bb,
                    "path": path,
                    "length_mm": length,
                }
            )
    components = {p["id"]: p for p in definition()["components"]}
    external_inputs = []
    external_outputs = []
    for net in definition()["nets"]:
        ends = net["endpoints"]
        if net["kind"] == "power" or not ends:
            continue
        driven = any(
            components[e["component"]]["package"]["pins"][e["pin"]]["direction"]
            == "output"
            for e in ends
        )
        if not driven:
            external_inputs.append(net["id"])
        elif len(ends) == 1:
            external_outputs.append(net["id"])
    return {
        "contacts": list(pins.values()),
        "chip_rects": rects,
        "wires": wires,
        "routing_diagnostics": diagnostics,
        "routed_mm": round(sum(w["length_mm"] for w in wires), 2),
        "crossings": crossing_count(wires),
        "external_inputs": external_inputs,
        "external_outputs": external_outputs,
    }


def evaluate(raw):
    if not isinstance(raw, dict) or set(raw) != {"settings", "boards", "placements"}:
        raise ValueError("배치 평가에는 settings, boards, placements가 필요합니다.")
    c = config(raw["settings"])
    boards = raw["boards"]
    placements = raw["placements"]
    # Reuse strict board validation, including finite bounded coordinates.
    config(c | {"topology": "custom", "custom_boards": boards})
    if not isinstance(placements, list) or any(
        not isinstance(p, dict) or set(p) != {"id", "board", "row", "rotation"}
        for p in placements
    ):
        raise ValueError("칩 배치 형식이 올바르지 않습니다.")
    validate_placements(placements, boards, c["row_gap"], c["grouping"])
    locked = {p["id"]: p for p in c["locks"]}
    if any(p["id"] in locked and p != locked[p["id"]] for p in placements):
        raise ValueError("고정한 칩이 이동했습니다.")
    m = estimate(placements, boards)
    return make_candidate("custom", placements, boards, m, c)


def make_candidate(topology, placements, boards, metrics, c):
    identity = json.dumps([boards, placements], sort_keys=True)
    return {
        "id": hashlib.sha256(identity.encode()).hexdigest()[:12],
        "topology": topology,
        "label": LABELS[topology],
        "boards": deepcopy(boards),
        "placements": deepcopy(placements),
        "metrics": metrics,
        "score": score(metrics, c["priority"]),
        **detailed(placements, boards),
    }


def search(raw):
    c = config(raw)
    start = time.monotonic()
    rng = random.Random(c["seed"])
    layouts = arrays(c)
    seeds = []
    for i in (0, 1):
        try:
            p = initial(c, i)
            validate_placements(p, layouts[0][1], c["row_gap"], c["grouping"])
            seeds.append(p)
        except ValueError:
            pass
    if not seeds:
        raise ValueError(
            "현재 고정·간격·그룹 조건에서 초기 배치를 찾지 못했습니다. 조건을 조정하세요."
        )
    locked = {p["id"] for p in c["locks"]}
    movable = [i for i, p in enumerate(seeds[0]) if p["id"] not in locked]
    evaluated = 0
    rejected = 0
    cache_hits = 0
    cache = {}
    pool = {}
    timed_out = False

    # Cache geometric estimates; a user may bound effort but never request an unbounded run.
    def consider(topology, boards, p):
        nonlocal evaluated, cache_hits
        key = json.dumps([boards, p], sort_keys=True)
        if key in cache:
            cache_hits += 1
            return cache[key]
        m = estimate(p, boards)
        s = score(m, c["priority"])
        evaluated += 1
        cache[key] = (s, m)
        pool[key] = (s, topology, boards, deepcopy(p), m)
        return s, m

    per = max(1, c["iterations"] // len(layouts))
    for topology, boards in layouts:
        states = []
        for p in seeds:
            validate_placements(p, boards, c["row_gap"], c["grouping"])
            s, m = consider(topology, boards, p)
            states.append((s, deepcopy(p)))
        current_score, current = min(states, key=lambda x: x[0])
        current = deepcopy(current)
        for step in range(per):
            if time.monotonic() - start > 12:
                timed_out = True
                break
            if not movable:
                break
            trial = deepcopy(current)
            i = rng.choice(movable)
            action = rng.randrange(5)
            if action == 0 and len(movable) > 1:
                j = rng.choice(movable)
                for key in ("board", "row"):
                    trial[i][key], trial[j][key] = trial[j][key], trial[i][key]
            elif action == 1:
                trial[i]["rotation"] = 180 - trial[i]["rotation"]
            elif action == 2:
                trial[i]["board"] = rng.randrange(c["board_count"])
                trial[i]["row"] = rng.randint(1, 56)
            elif action == 3:
                board = trial[i]["board"]
                delta = rng.choice([-5, -2, 2, 5])
                for p in trial:
                    if p["board"] == board and p["id"] not in locked:
                        p["row"] += delta
            else:
                trial[i]["row"] += rng.choice([-5, -2, -1, 1, 2, 5])
            try:
                validate_placements(trial, boards, c["row_gap"], c["grouping"])
            except ValueError:
                rejected += 1
                continue
            s, _ = consider(topology, boards, trial)
            temperature = 30 * (1 - step / max(1, per)) + 0.1
            if s < current_score or rng.random() < math.exp(
                min(0, (current_score - s) / temperature)
            ):
                current_score, current = s, trial
        if timed_out:
            break
    ranked = sorted(pool.values(), key=lambda x: x[0])
    chosen = []
    seen = set()

    def add(v):
        key = json.dumps([v[2], v[3]], sort_keys=True)
        if key not in seen:
            seen.add(key)
            chosen.append(v)

    # Show the best sampled candidate from each array family, plus alternatives.
    for topology in dict.fromkeys(v[1] for v in ranked):
        add(next(v for v in ranked if v[1] == topology))
    add(min(ranked, key=lambda v: v[4]["estimated_mm"]))
    add(min(ranked, key=lambda v: (v[4]["readability_penalty"], v[0])))
    for v in ranked:
        if len(chosen) >= 8:
            break
        add(v)
    candidates = [
        make_candidate(t, p, b, m, c)
        for s, t, b, p, m in sorted(chosen, key=lambda v: v[0])
    ]
    return {
        "version": VERSION,
        "profile": PROFILE,
        "settings": c,
        "candidates": candidates,
        "limitations": LIMITATIONS,
        "statistics": {
            "evaluated": evaluated,
            "rejected": rejected,
            "cache_hits": cache_hits,
            "layouts": len(layouts),
            "wall_seconds": round(time.monotonic() - start, 3),
            "bounded_early": timed_out,
        },
        "objective": "신호 넷 MST 맨해튼 길이 + 가독성 벌점 + 보드 간 점퍼 벌점. 상세 경로는 후보 생성 후 별도로 검증.",
    }
