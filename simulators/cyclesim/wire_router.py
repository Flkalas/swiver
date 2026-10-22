"""Bounded orthogonal jumper routing with separate tracks and explicit crossings.

Coordinates are planar drawing guides, not a wire-height or physical DRC model.
Electrical junctions only exist at assigned breadboard strips, never along paths.
"""

import heapq
import math
from bisect import bisect_left, bisect_right
from itertools import pairwise

TRACK = 0.635  # Quarter of a 2.54 mm breadboard pitch; drawing track spacing.
EPS = 1e-6


def segments(path):
    return list(pairwise(path))


def simplify(path):
    out = []
    for p in path:
        p = [round(p[0], 3), round(p[1], 3)]
        if out and p == out[-1]:
            continue
        if len(out) >= 2 and (
            out[-2][0] == out[-1][0] == p[0] or out[-2][1] == out[-1][1] == p[1]
        ):
            # Do not allow a backtracking spur to disappear into another wire.
            if (out[-1][0] - out[-2][0]) * (p[0] - out[-1][0]) + (
                out[-1][1] - out[-2][1]
            ) * (p[1] - out[-1][1]) < 0:
                return None
            out[-1] = p
        else:
            out.append(p)
    return out


def distance(path):
    return sum(abs(a[0] - b[0]) + abs(a[1] - b[1]) for a, b in segments(path))


def simple_path(path):
    spans = segments(path)
    return all(
        intersection(a, b, c, d) is None
        for i, (a, b) in enumerate(spans)
        for c, d in spans[i + 2 :]
    )


def intersection(a, b, c, d):
    """Return overlap/touch/cross for two axis-aligned nonzero segments."""
    ah, ch = a[1] == b[1], c[1] == d[1]
    if ah == ch:
        axis = 0 if ah else 1
        if abs(a[1 - axis] - c[1 - axis]) > EPS:
            return None
        lo = max(min(a[axis], b[axis]), min(c[axis], d[axis]))
        hi = min(max(a[axis], b[axis]), max(c[axis], d[axis]))
        if hi < lo - EPS:
            return None
        return ("overlap" if hi > lo + EPS else "touch", None)
    if not ah:
        a, b, c, d = c, d, a, b
    x, y = c[0], a[1]
    ax0, ax1 = sorted((a[0], b[0]))
    cy0, cy1 = sorted((c[1], d[1]))
    if ax0 - EPS <= x <= ax1 + EPS and cy0 - EPS <= y <= cy1 + EPS:
        strict = ax0 + EPS < x < ax1 - EPS and cy0 + EPS < y < cy1 - EPS
        return ("cross" if strict else "touch", [x, y])
    return None


def audit(wires):
    crossings, overlaps, touches = [], 0, 0
    for i, w in enumerate(wires):
        for old in wires[:i]:
            seen = set()
            for a, b in segments(w["path"]):
                for c, d in segments(old["path"]):
                    hit = intersection(a, b, c, d)
                    if not hit:
                        continue
                    kind, xy = hit
                    if kind == "overlap":
                        overlaps += 1
                    elif kind == "touch":
                        touches += 1
                    elif tuple(xy) not in seen:
                        seen.add(tuple(xy))
                        crossings.append(
                            {"xy": xy, "over": w["id"], "under": old["id"]}
                        )
    return {
        "crossings": len(crossings),
        "crossing_points": crossings,
        "overlap_count": overlaps,
        "unintended_contacts": touches,
    }


class Router:
    def __init__(self, rects, terminals):
        self.rects = rects
        self.terminals = set(map(tuple, terminals))
        self.h, self.v = {}, {}
        self.hkeys, self.vkeys = [], []
        self.point_rows, self.point_cols = {}, {}
        for x, y in self.terminals:
            self.point_rows.setdefault(y, []).append(x)
            self.point_cols.setdefault(x, []).append(y)
        for table in (self.point_rows, self.point_cols):
            for row in table.values():
                row.sort()
        self.lanes = [set(), set()]
        for r in rects:
            for axis in (0, 1):
                for delta in (TRACK, 2 * TRACK, 3 * TRACK, 4 * TRACK):
                    self.lanes[axis].add(round(r[axis] - delta, 3))
                    self.lanes[axis].add(round(r[axis + 2] + delta, 3))

    def assess(self, path, grid=False):
        crossed = set()
        for a, b in segments(path):
            horizontal = a[1] == b[1]
            axis = 0 if horizontal else 1
            lo, hi = sorted((a[axis], b[axis]))
            fixed = a[1 - axis]
            for r in self.rects:
                if (
                    r[1 - axis] < fixed < r[3 - axis]
                    and max(lo, r[axis]) < min(hi, r[axis + 2]) - EPS
                ):
                    return None
            # Another plug or IC pin is not a legal junction or pass-through.
            points = (self.point_rows if horizontal else self.point_cols).get(fixed, [])
            if bisect_right(points, lo + EPS) < bisect_left(points, hi - EPS):
                return None
            if (
                tuple(a) in self.terminals
                and a != path[0]
                or tuple(b) in self.terminals
                and b != path[-1]
            ):
                return None
            parallel = self.h if horizontal else self.v
            keys = self.hkeys if horizontal else self.vkeys
            for k in keys[
                bisect_left(keys, fixed - TRACK + EPS) : bisect_right(
                    keys, fixed + TRACK - EPS
                )
            ]:
                for start, end, _ in parallel[k]:
                    if min(hi, end) >= max(lo, start) - EPS:
                        return None
            perpendicular = self.v if horizontal else self.h
            keys = self.vkeys if horizontal else self.hkeys
            for k in keys[bisect_left(keys, lo - EPS) : bisect_right(keys, hi + EPS)]:
                for start, end, wire_id in perpendicular[k]:
                    if start - EPS <= fixed <= end + EPS:
                        if (
                            grid or lo + EPS < k < hi - EPS
                        ) and start + EPS < fixed < end - EPS:
                            crossed.add((wire_id, k, fixed))
                        else:
                            return None
        return len(crossed)

    def grid_route(self, a, b, budget=40000, margin=12):
        """Bounded local visibility grid for routes needing several bends."""
        coords = []
        for axis in (0, 1):
            lo, hi = min(a[axis], b[axis]) - margin, max(a[axis], b[axis]) + margin
            values = {a[axis], b[axis], round(lo, 3), round(hi, 3)}
            values.update(v for v in self.lanes[axis] if lo <= v <= hi)
            values.update(
                round(p[axis] + delta, 3)
                for p in self.terminals
                for delta in (-TRACK, 0, TRACK)
                if lo <= p[axis] + delta <= hi
            )
            coords.append(sorted(values))
        xs, ys = coords
        start = (xs.index(a[0]), ys.index(a[1]), 2)
        goal = (xs.index(b[0]), ys.index(b[1]))
        costs, previous, edge_cache = {start: 0}, {}, {}
        queue = [(abs(a[0] - b[0]) + abs(a[1] - b[1]), 0, start)]
        steps = 0
        while queue and steps < budget:
            _, cost, state = heapq.heappop(queue)
            if cost != costs.get(state):
                continue
            steps += 1
            x, y, direction = state
            if (x, y) == goal:
                path = [[xs[x], ys[y]]]
                while state in previous:
                    state = previous[state]
                    path.append([xs[state[0]], ys[state[1]]])
                path = simplify(list(reversed(path)))
                return (
                    path
                    if path and simple_path(path) and self.assess(path) is not None
                    else None
                )
            for dx, dy, axis in ((1, 0, 0), (-1, 0, 0), (0, 1, 1), (0, -1, 1)):
                xx, yy = x + dx, y + dy
                if not 0 <= xx < len(xs) or not 0 <= yy < len(ys):
                    continue
                end = (xs[xx], ys[yy])
                if end in self.terminals and (xx, yy) != goal:
                    continue
                key = tuple(sorted(((x, y), (xx, yy))))
                if key not in edge_cache:
                    edge_cache[key] = self.assess(
                        [[xs[x], ys[y]], list(end)], grid=True
                    )
                crosses = edge_cache[key]
                if crosses is None:
                    continue
                value = cost + abs(xs[xx] - xs[x]) + abs(ys[yy] - ys[y]) + 18 * crosses
                if direction != 2 and direction != axis:
                    value += 2
                target = (xx, yy, axis)
                if value < costs.get(target, math.inf):
                    costs[target] = value
                    previous[target] = (x, y, direction)
                    h = abs(xs[xx] - b[0]) + abs(ys[yy] - b[1])
                    heapq.heappush(queue, (value + h, value, target))
        return None

    def commit(self, path, wire_id):
        for a, b in segments(path):
            horizontal = a[1] == b[1]
            axis = 0 if horizontal else 1
            lo, hi = sorted((a[axis], b[axis]))
            (self.h if horizontal else self.v).setdefault(a[1 - axis], []).append(
                (lo, hi, wire_id)
            )
        self.hkeys, self.vkeys = sorted(self.h), sorted(self.v)

    def route(self, a, b):
        best, cost = None, math.inf
        seen = set()

        def consider(raw):
            nonlocal best, cost
            path = simplify(raw)
            if path is None or len(path) < 2:
                return
            key = tuple(map(tuple, path))
            if key in seen:
                return
            seen.add(key)
            length = distance(path)
            base = length + 2 * max(0, len(path) - 2)
            if base >= cost:
                return
            if not simple_path(path):
                return
            crosses = self.assess(path)
            if crosses is None:
                return
            value = base + 18 * crosses
            if value < cost:
                cost, best = value, path

        consider([a, [a[0], b[1]], b])
        consider([a, [b[0], a[1]], b])
        lanes = []
        for axis in (0, 1):
            values = self.lanes[axis] | {
                round(p[axis] + sign * TRACK * n, 3)
                for p in (a, b)
                for sign in (-1, 1)
                for n in (1, 2, 4, 8)
            }
            values = sorted(
                values, key=lambda x: (abs(x - a[axis]) + abs(x - b[axis]), x)
            )
            lanes.append(values)
            for v in values:
                if axis == 0:
                    consider([a, [v, a[1]], [v, b[1]], b])
                else:
                    consider([a, [a[0], v], [b[0], v], b])
        # Short endpoint escapes split otherwise collinear terminal fanout.
        # Bound port/lane combinations; no unbounded global auto-routing.
        for axis in (0, 1):
            for sign_a in (-1, 1):
                for sign_b in (-1, 1):
                    aa, bb = list(a), list(b)
                    aa[axis] = round(aa[axis] + sign_a * TRACK, 3)
                    bb[axis] = round(bb[axis] + sign_b * TRACK, 3)
                    consider([a, aa, [aa[0], bb[1]], bb, b])
                    consider([a, aa, [bb[0], aa[1]], bb, b])
                    for v in lanes[1 - axis][:28]:
                        if axis == 0:
                            consider([a, aa, [aa[0], v], [bb[0], v], bb, b])
                        else:
                            consider([a, aa, [v, aa[1]], [v, bb[1]], bb, b])
        if best is not None:
            return best, round(distance(best), 2)
        best = self.grid_route(a, b)
        if best is None:
            best = self.grid_route(a, b, budget=80000, margin=60)
        if best is not None:
            return best, round(distance(best), 2)
        return None, None
