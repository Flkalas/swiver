"""Real browser acceptance of placement exploration, locking and file roundtrips."""

import csv
import json
import math
import threading
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

from simulators.cyclesim.viewer_server import ViewerServer

OUT = Path(__file__).with_name("build") / "viewer-evidence"


def check_crossing_markers(page, candidate):
    markers = page.locator(".bb-crossing").evaluate_all("""els => els.map(e => {
      const gap=e.querySelector('circle'), line=e.querySelector('line');
      return {over:e.dataset.over,under:e.dataset.under,
        xy:[+gap.getAttribute('cx'),+gap.getAttribute('cy')],r:+gap.getAttribute('r'),
        start:[+line.getAttribute('x1'),+line.getAttribute('y1')],
        end:[+line.getAttribute('x2'),+line.getAttribute('y2')]};
    })""")
    wires = {w["id"]: w for w in candidate["wires"]}
    for marker in markers:
        assert 0 < marker["r"] <= 0.8
        x, y = marker["xy"]
        found = False
        for w in wires.values():
            for a, b in zip(w["path"], w["path"][1:]):
                px = max(min(a[0], b[0]), min(x, max(a[0], b[0])))
                py = max(min(a[1], b[1]), min(y, max(a[1], b[1])))
                distance = math.hypot(px - x, py - y)
                if w["id"] in (marker["over"], marker["under"]) and distance < 1e-6:
                    if w["id"] == marker["over"]:
                        assert all(
                            (p[0] == a[0] == b[0] or p[1] == a[1] == b[1])
                            and all(
                                min(a[k], b[k]) <= p[k] <= max(a[k], b[k])
                                for k in (0, 1)
                            )
                            for p in (marker["start"], marker["end"])
                        )
                        found = True
                    continue
                assert distance > marker["r"] * 2, (marker, w["id"])
        assert found


def run():
    OUT.mkdir(exist_ok=True, parents=True)
    checks = []
    errors = []
    with ViewerServer(0) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch()
                page = browser.new_page(
                    viewport={"width": 1440, "height": 900}, accept_downloads=True
                )
                page.set_default_timeout(10000)
                page.on("pageerror", lambda e: errors.append(str(e)))
                page.on(
                    "console",
                    lambda msg: (
                        errors.append(msg.text)
                        if "Content Security Policy" in msg.text
                        else None
                    ),
                )
                page.goto(f"http://127.0.0.1:{server.server_port}")
                expect(page.locator("#status-banner")).to_have_class(
                    "status-banner live"
                )
                with page.expect_response(
                    "**/api/placement/search", timeout=25000
                ) as response:
                    page.locator("#view-placement").click()
                data = response.value.json()
                assert response.value.ok
                expect(page.locator(".bb-chip")).to_have_count(12)
                expect(page.locator(".bb-hole")).to_have_count(5 * 830)
                expect(page.locator("#place-topology")).to_have_value("compact221")
                expect(page.locator("#place-gap_mm")).to_have_value("0")
                expect(page.locator("#place-gap_mm")).not_to_be_editable()
                expect(page.locator("#placement-cluster-note")).to_contain_text(
                    "4.98 mm"
                )
                first = data["candidates"][0]
                assert len(first["wires"]) == 90 and not first["routing_diagnostics"]
                assert first["overlap_count"] == first["unintended_contacts"] == 0
                page.locator("#placement-net").select_option("net_bctrl0")
                expect(page.locator(".bb-wire")).to_have_count(7)
                expect(page.locator(".bb-end")).to_have_count(14)
                expect(page.locator(".bb-strip")).to_have_count(8)
                expect(page.locator(".placement-net-relation")).to_contain_text(
                    "각각 다른 구멍"
                )
                page.locator("#placement-all-wires").check()
                expect(page.locator(".bb-wire")).to_have_count(90)
                expect(page.locator(".bb-crossing")).to_have_count(first["crossings"])
                expect(page.locator(".bb-end")).to_have_count(180)
                check_crossing_markers(page, first)
                assert page.locator(".bb-wire-line").evaluate_all(
                    "els => els.every(e => getComputedStyle(e).stroke !== 'none')"
                )
                selected = next(w for w in first["wires"] if w["net"] == "net_bctrl0")
                page.locator(f'[data-wire-select="{selected["id"]}"]').click()
                expect(page.locator(".bb-wire.selected")).to_have_count(1)
                expect(page.locator(".bb-wire.selected")).to_have_attribute(
                    "data-place-wire", selected["id"]
                )
                expect(page.locator(".bb-end-label")).to_have_count(2)
                expect(page.locator(".bb-end-label").first).to_contain_text(
                    selected["from"]["hole"]
                )
                coordinates = page.locator(
                    f'[data-end-wire="{selected["id"]}"]'
                ).evaluate_all(
                    "els => els.map(e => [+e.getAttribute('cx'), +e.getAttribute('cy')])"
                )
                assert coordinates == [selected["from"]["xy"], selected["to"]["xy"]]
                page.keyboard.press("Escape")
                expect(page.locator(".bb-wire.selected")).to_have_count(0)
                page.locator(f'[data-place-wire="{selected["id"]}"]').focus()
                page.keyboard.press("Enter")
                expect(
                    page.locator(f'[data-place-wire="{selected["id"]}"]')
                ).to_be_focused()
                expect(page.locator(".bb-wire.selected")).to_have_count(1)
                page.keyboard.press("Escape")
                # Two default parallel tracks are only 0.635 mm apart. The old
                # 2.5 mm transparent hit area picked J041 when clicking J027.
                point = page.locator("#placement-map").evaluate(
                    "e => {const p=new DOMPoint(37.025,195).matrixTransform(e.getScreenCTM()); return [p.x,p.y];}"
                )
                page.mouse.click(*point)
                expect(page.locator(".bb-wire.selected")).to_have_attribute(
                    "data-place-wire", "J027"
                )
                page.keyboard.press("Escape")
                page.locator("#placement-net").select_option("net_bctrl0")
                page.locator("#placement-all-wires").uncheck()
                checks.append(
                    "90 jumpers: separate holes, internal strips, geometry-safe crossing breaks, nearest-wire mouse picking and keyboard selection"
                )
                for width, height in ((1440, 900), (1280, 800)):
                    page.set_viewport_size({"width": width, "height": height})
                    assert page.evaluate(
                        "document.documentElement.scrollWidth <= innerWidth"
                    )
                    page.screenshot(
                        path=str(OUT / f"routing-net-{width}x{height}.png"),
                        full_page=True,
                    )
                before = page.locator("#placement-map").get_attribute("viewBox")
                page.locator("#placement-net").select_option("net_c_lo")
                page.locator("#placement-all-wires").check()
                carry = next(w for w in first["wires"] if w["net"] == "net_c_lo")
                page.locator(f'[data-wire-select="{carry["id"]}"]').click()
                page.locator("#placement-fit-cluster").click()
                assert page.locator("#placement-map").get_attribute("viewBox") != before
                page.locator(".placement-content").screenshot(
                    path=str(OUT / "routing-cluster-detail.png")
                )
                page.locator("#placement-fit").click()
                page.keyboard.press("Escape")
                page.locator("#placement-all-wires").check()
                page.locator(".placement-content").screenshot(
                    path=str(OUT / "routing-all-wires.png")
                )
                page.locator("#placement-all-wires").uncheck()
                page.locator("#placement-net").select_option("net_c_lo")
                (OUT / "routing-default.json").write_text(
                    json.dumps(first, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                checks.append(
                    "default five-board layout: fixed zero board gap, 4.98 mm adder body gap and cluster zoom"
                )

                page.locator("#place-edge_rows").fill("2")
                page.locator("#place-orientation").select_option("90")
                with page.expect_response(
                    "**/api/placement/search", timeout=25000
                ) as response:
                    page.locator("#placement-search").click()
                compact = response.value.json()
                assert response.value.ok
                assert all(
                    next(p for p in c["placements"] if p["id"] == "U_ALU_283_LO")["row"]
                    == 54
                    for c in compact["candidates"]
                )
                expect(page.locator("#placement-cluster-note")).to_contain_text(
                    "15.14 mm"
                )
                page.locator("#placement-chip-picker").select_option("U_ALU_283_LO")
                page.locator("#placement-chip-row").fill("28")
                with page.expect_response("**/api/placement/evaluate") as response:
                    page.locator("#placement-apply-chip").click()
                assert response.value.status == 400
                expect(page.locator("#placement-status")).to_contain_text("안쪽 모음")
                checks.append(
                    "clearance and rigid 90 degree rotation work; manual adder central drift rejected"
                )

                page.locator("#place-topology").select_option("all")
                page.locator("#place-board_count").select_option("4")
                page.locator("#place-orientation").select_option("auto")
                with page.expect_response(
                    "**/api/placement/search", timeout=25000
                ) as response:
                    page.locator("#placement-search").click()
                data = response.value.json()
                assert response.value.ok
                expect(page.locator(".bb-hole")).to_have_count(4 * 830)
                assert len(data["candidates"]) >= 4
                expect(page.locator("#placement-wire-list")).to_contain_text("9번 COUT")
                expect(page.locator("#placement-wire-list")).to_contain_text("7번 CIN")
                checks.append(
                    "generic 8-2-2 search: four array families, 12 chips, 3320 holes and carry contacts"
                )

                page.locator("#placement-candidates button").nth(-1).click()
                page.locator("#placement-net").select_option("net_b_add0")
                expect(page.locator("#placement-wire-list")).to_contain_text(
                    "153_0 9번 2Y"
                )
                expect(page.locator("#placement-wire-list")).to_contain_text(
                    "283_LO 6번 B0"
                )
                page.locator("#placement-all-wires").check()
                expect(page.locator(".bb-wire")).to_have_count(90)
                page.locator("#placement-all-wires").uncheck()
                page.locator("#placement-chip-picker").select_option("U_ALU_153_0")
                before = page.locator("#placement-map").get_attribute("viewBox")
                page.locator("#placement-fit-chip").click()
                assert page.locator("#placement-map").get_attribute("viewBox") != before
                page.locator("#placement-fit").click()
                page.locator("#placement-chip-lock").check()
                with page.expect_response("**/api/placement/evaluate") as response:
                    page.locator("#placement-apply-chip").click()
                assert response.value.ok
                expect(page.locator("#placement-locks")).to_contain_text("1개 칩 고정")
                page.locator("#place-iterations").fill("80")
                with page.expect_response(
                    "**/api/placement/search", timeout=25000
                ) as response:
                    page.locator("#placement-search").click()
                data = response.value.json()
                assert response.value.ok
                lock = data["settings"]["locks"][0]
                assert all(
                    next(p for p in c["placements"] if p["id"] == lock["id"]) == lock
                    for c in data["candidates"]
                )
                checks.append(
                    "candidate/net selection, all wires, chip zoom and pinning across a new search"
                )

                page.locator("#placement-chip-picker").select_option("U_ALU_153_0")
                page.locator("#placement-chip-row").fill("0")
                with page.expect_response("**/api/placement/evaluate") as response:
                    page.locator("#placement-apply-chip").click()
                assert response.value.status == 400
                expect(page.locator("#placement-status")).to_contain_text(
                    "이전 결과를 유지"
                )
                expect(page.locator(".bb-chip")).to_have_count(12)
                page.get_by_text(
                    "보드 좌표 직접 편집 — 자유로운 지그재그 배열", exact=True
                ).click()
                first = data["candidates"][0]
                fields = page.locator('[data-board-edit="1"]')
                fields.locator('[data-axis="x"]').fill(str(first["boards"][0]["x"]))
                fields.locator('[data-axis="y"]').fill(str(first["boards"][0]["y"]))
                with page.expect_response("**/api/placement/evaluate") as response:
                    page.locator("#placement-apply-boards").click()
                assert response.value.status == 400
                expect(page.locator("#placement-status")).to_contain_text("겹")
                far_x = (
                    max(
                        b["x"] + (165 if b["rotation"] % 180 else 55)
                        for b in first["boards"]
                    )
                    + 30
                )
                fields.locator('[data-axis="x"]').fill(str(far_x))
                with page.expect_response("**/api/placement/evaluate") as response:
                    page.locator("#placement-apply-boards").click()
                assert response.value.status == 400
                expect(page.locator("#placement-status")).to_contain_text("0 mm")
                # A rigid translation keeps every board joined and is allowed.
                for b in first["boards"]:
                    row = page.locator(f'[data-board-edit="{b["id"]}"]')
                    row.locator('[data-axis="x"]').fill(str(b["x"] + 5))
                    row.locator('[data-axis="y"]').fill(str(b["y"] + 7))
                with page.expect_response("**/api/placement/evaluate") as response:
                    page.locator("#placement-apply-boards").click()
                custom = response.value.json()
                assert response.value.ok
                expect(page.locator("#place-topology")).to_have_value("custom")
                checks.append(
                    "invalid row, overlapping and disconnected boards rejected; joined board translation accepted"
                )

                with page.expect_download() as download:
                    page.locator("#placement-export").click()
                saved = OUT / "placement-roundtrip.json"
                download.value.save_as(saved)
                exported = json.loads(saved.read_text(encoding="utf-8"))
                assert len(exported["placements"]) == 12
                with page.expect_download() as download:
                    page.locator("#placement-csv").click()
                wire_file = OUT / "placement-jumpers.csv"
                download.value.save_as(wire_file)
                rows = list(
                    csv.reader(wire_file.open(encoding="utf-8-sig", newline=""))
                )
                assert len(rows) == len(custom["candidate"]["wires"]) + 1
                assert rows[0][:3] == ["wire_id", "color", "net"]
                assert {row[0] for row in rows[1:]} == {
                    w["id"] for w in custom["candidate"]["wires"]
                }
                page.locator("#place-seed").fill("840")
                with page.expect_response("**/api/placement/evaluate") as response:
                    page.locator("#placement-import").set_input_files(saved)
                imported = response.value.json()
                assert response.value.ok
                assert imported["candidate"]["placements"] == exported["placements"]
                assert imported["candidate"]["boards"] == exported["boards"]
                expect(page.locator("#place-seed")).to_have_value(
                    str(exported["settings"]["seed"])
                )
                checks.append(
                    "JSON export/import revalidates the exact placements; signal CSV lists evaluated jumper endpoints"
                )

                page.route("**/api/placement/search", lambda route: route.abort())
                page.locator("#placement-search").click()
                expect(page.locator("#placement-status")).to_have_class(
                    "placement-status error"
                )
                expect(page.locator(".bb-chip")).to_have_count(12)
                page.unroute("**/api/placement/search")
                pending = []
                page.route(
                    "**/api/placement/search", lambda route: pending.append(route)
                )
                page.locator("#placement-search").click()
                page.wait_for_function(
                    "document.getElementById('placement-search').disabled"
                )
                page.locator("#place-seed").fill("841")
                assert pending
                pending[0].fulfill(
                    json={
                        **data,
                        "request_id": pending[0].request.post_data_json["request_id"],
                    }
                )
                expect(page.locator("#placement-search")).to_be_enabled()
                expect(page.locator("#placement-status")).to_contain_text("설정 변경됨")
                expect(page.locator("#place-seed")).to_have_value("841")
                page.unroute("**/api/placement/search")
                checks.append(
                    "failed search retains prior layout; stale delayed response cannot replace changed settings"
                )

                page.locator("#placement-unlock").click()
                page.locator("#place-topology").select_option("zigzag")
                page.locator("#place-grouping").select_option("stages")
                page.locator("#place-board_count").select_option("4")
                with page.expect_response(
                    "**/api/placement/search", timeout=25000
                ) as response:
                    page.locator("#placement-search").click()
                assert response.value.ok
                page.locator("#placement-net").select_option("net_c_lo")
                for width, height in ((1440, 900), (1280, 800), (390, 844)):
                    page.set_viewport_size({"width": width, "height": height})
                    page.locator("#placement-fit").click()
                    assert page.evaluate(
                        "document.documentElement.scrollWidth <= innerWidth"
                    )
                    page.screenshot(
                        path=str(OUT / f"routing-zigzag-{width}x{height}.png"),
                        full_page=True,
                    )
                checks.append(
                    "zigzag stage-grouped layout renders at 1440x900, 1280x800 and mobile without horizontal page overflow"
                )
                assert not errors, errors
                browser.close()
        finally:
            server.shutdown()
            thread.join(timeout=3)
    (OUT / "routing-browser-checks.json").write_text(
        json.dumps(
            {"checks": checks, "page_errors": errors}, ensure_ascii=False, indent=2
        ),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {"passed": len(checks), "checks": checks}, ensure_ascii=False, indent=2
        )
    )


if __name__ == "__main__":
    run()
