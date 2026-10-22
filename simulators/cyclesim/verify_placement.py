"""Real browser acceptance of placement exploration, locking and file roundtrips."""

import csv
import json
from pathlib import Path
import threading

from playwright.sync_api import expect, sync_playwright
from simulators.cyclesim.viewer_server import ViewerServer

OUT = Path(__file__).with_name("build") / "viewer-evidence"


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
                page.goto(f"http://127.0.0.1:{server.server_port}")
                expect(page.locator("#status-banner")).to_have_class(
                    "status-banner live"
                )
                with page.expect_response("**/api/placement/search") as response:
                    page.locator("#view-placement").click()
                data = response.value.json()
                assert response.value.ok
                expect(page.locator(".bb-chip")).to_have_count(12)
                expect(page.locator(".bb-hole")).to_have_count(4 * 830)
                assert len(data["candidates"]) >= 4
                expect(page.locator("#placement-wire-list")).to_contain_text("9번 COUT")
                expect(page.locator("#placement-wire-list")).to_contain_text("7번 CIN")
                checks.append(
                    "default 8-2-2 search: four array families, 12 chips, 3320 holes and carry contacts"
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
                with page.expect_response("**/api/placement/search") as response:
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
                custom = response.value.json()
                assert response.value.ok
                expect(page.locator("#place-topology")).to_have_value("custom")
                checks.append(
                    "invalid row and overlapping boards rejected; independent board coordinates accepted"
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
                page.locator("#place-gap_mm").fill("20")
                with page.expect_response("**/api/placement/evaluate") as response:
                    page.locator("#placement-import").set_input_files(saved)
                imported = response.value.json()
                assert response.value.ok
                assert imported["candidate"]["placements"] == exported["placements"]
                assert imported["candidate"]["boards"] == exported["boards"]
                expect(page.locator("#place-gap_mm")).to_have_value(
                    str(exported["settings"]["gap_mm"]).removesuffix(".0")
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
                page.locator("#place-gap_mm").fill("21")
                assert pending
                pending[0].fulfill(
                    json={
                        **data,
                        "request_id": pending[0].request.post_data_json["request_id"],
                    }
                )
                expect(page.locator("#placement-search")).to_be_enabled()
                expect(page.locator("#placement-status")).to_contain_text("설정 변경됨")
                expect(page.locator("#place-gap_mm")).to_have_value("21")
                page.unroute("**/api/placement/search")
                checks.append(
                    "failed search retains prior layout; stale delayed response cannot replace changed settings"
                )

                page.locator("#placement-unlock").click()
                page.locator("#place-topology").select_option("zigzag")
                page.locator("#place-gap_mm").fill("6")
                page.locator("#place-grouping").select_option("stages")
                page.locator("#place-board_count").select_option("4")
                with page.expect_response("**/api/placement/search") as response:
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
                        path=str(OUT / f"placement-{width}x{height}.png"),
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
    (OUT / "placement-checks.json").write_text(
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
