"""Real-browser acceptance checks; run explicitly after installing Playwright.

python -m simulators.cyclesim.verify_viewer
The server is ephemeral, loopback only, and always shut down on completion.
Screenshots and a compact result record go to build/viewer-evidence.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

from simulators.cyclesim.viewer_model import AluSession
from simulators.cyclesim.viewer_server import ViewerServer

OUT = Path(__file__).with_name("build") / "viewer-evidence"


def run():
    OUT.mkdir(parents=True, exist_ok=True)
    checks = []
    with ViewerServer(0) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch()
                page = browser.new_page(viewport={"width": 1440, "height": 900})
                page.set_default_timeout(8000)
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                url = f"http://127.0.0.1:{server.server_port}"
                page.goto(url)
                expect(page.locator("#status-banner")).to_have_class("status-banner live")
                expect(page.locator("[data-component]")).to_have_count(12)
                y = page.locator('[data-observe-bus="y"] .bus-value')

                def edit(selector, value):
                    with page.expect_response("**/api/input") as response:
                        if selector == "#operation":
                            page.locator(selector).select_option(value)
                        else:
                            page.locator(selector).fill(value)
                    data = response.value.json()
                    assert response.value.ok, data
                    expect(page.locator("#status-banner")).to_have_class("status-banner live")
                    expect(y).to_have_text(str(data["buses"]["y"]["value"]))
                    return data

                edit("#a-hex", "FF")
                result = edit("#b-dec", "1")
                assert result["signals"]["net_c_hi"] == "1"
                expect(y).to_have_text("0")
                edit("#a-dec", "15")
                result = edit("#operation", "ADD")
                assert result["signals"]["net_c_lo"] == "1"
                edit("#a-dec", "3")
                edit("#b-dec", "5")
                result = edit("#operation", "SUB")
                assert result["buses"]["y"]["value"] == 254 and result["signals"]["net_c_hi"] == "0"
                edit("#a-dec", "5")
                result = edit("#operation", "CMP")
                assert result["comparison_flags"]["zero"] and not result["cpu_policy"]["acc_write"]
                edit("#a-hex", "AA")
                edit("#b-hex", "55")
                result = edit("#operation", "XOR")
                assert result["buses"]["y"]["value"] == 255
                with page.expect_response("**/api/input"):
                    page.locator('#a-bits [data-bit="0"]').click()
                expect(y).to_have_text("254")
                checks.append("hex/decimal inputs, presets, overflow, nibble carry, borrow, CMP, XOR, bit toggle")

                # Direct mode and its server-side observation.
                with page.expect_response("**/api/input"):
                    page.locator("#mode-direct").click()
                edit("#lgc", "10")
                expect(y).to_have_text("171")
                expect(page.locator("#cpu-policy")).to_contain_text("정책 없음")
                checks.append("direct controls and separate CPU policy")

                page.locator('[data-component="U_ALU_153_0"]').click()
                expect(page.locator("#inspector-body")).to_contain_text("U_ALU_153_0")
                page.locator('[data-pin-component="U_ALU_153_0"][data-pin="A"]').press("Enter")
                expect(page.locator("#inspector-body")).to_contain_text("U_ALU_283_LO")
                page.locator("#clear-selection").click()
                page.locator('[data-component="U_ALU_153_0"]').click()
                page.locator('[data-inspect-net="net_a0"]').first.click()
                expect(page.locator("#inspector-body")).to_contain_text("U_ALU_283_LO")
                page.locator("#clear-selection").click()
                page.locator("#net-search").fill("net_c_lo")
                with page.expect_response("**/api/snapshot"):
                    page.wait_for_timeout(3200)
                expect(page.locator("#net-search")).to_have_value("net_c_lo")
                page.locator('#net-results [data-inspect-net="net_c_lo"]').click()
                expect(page.locator("#inspector-body")).to_contain_text("U_ALU_283_HI")
                page.locator('[data-trace="7"]').click()
                page.locator("#zoom-in").click()
                page.locator("#fit-selection").click()
                page.locator("#fit").click()
                checks.append("chip, net search, fanout inspector, bit 7, zoom and selection fit")

                # Rejected edits must retain the last observation and invalid text.
                before = y.inner_text()
                for invalid in ("256", "-1", "1.5", "", "12junk"):
                    page.locator("#a-dec").fill(invalid)
                    expect(page.locator("#input-error")).to_be_visible()
                    expect(y).to_have_text(before)
                    expect(page.locator("#a-dec")).to_have_value(invalid)
                with page.expect_response("**/api/reset"):
                    page.locator("#reset").click()
                expect(y).to_have_text("0")
                expect(page.locator("#a-dec")).to_have_value("0")
                expect(page.locator("#operation")).to_have_value("ADD")
                checks.append("invalid input retention and reset")

                # Hold an old HTTP response; an invalid edit must invalidate it.
                held = []

                def hold(route):
                    response = route.fetch()
                    held.append((route, response))

                page.route("**/api/input", hold)
                page.locator("#a-dec").fill("42")
                page.wait_for_timeout(350)
                assert held, "write was not issued"
                page.locator("#a-dec").fill("256")
                route, response = held.pop()
                route.fulfill(response=response)
                page.wait_for_timeout(100)
                expect(page.locator("#a-dec")).to_have_value("256")
                expect(page.locator("#input-error")).to_be_visible()
                expect(y).to_have_text("0")
                page.unroute("**/api/input", hold)
                edit("#a-dec", "7")
                checks.append("old response after invalid edit cannot overwrite state or diagnostics")

                valid_held = []

                def hold_first(route):
                    if valid_held:
                        route.continue_()
                    else:
                        valid_held.append((route, route.fetch()))

                page.route("**/api/input", hold_first)
                page.locator("#a-dec").fill("20")
                page.wait_for_timeout(350)
                assert valid_held
                page.locator("#a-dec").fill("21")
                route, response = valid_held[0]
                route.fulfill(response=response)
                expect(page.locator("#a-dec")).to_have_value("21")
                expect(y).to_have_text("21")
                page.unroute("**/api/input", hold_first)
                edit("#a-dec", "7")
                checks.append("superseded valid response cannot replace newer draft")

                # No edits are required to detect a disconnected server.
                page.route("**/api/snapshot", lambda route: route.abort())
                expect(page.locator("#status-banner")).to_have_class("status-banner error", timeout=10000)
                expect(y).to_have_text("7")
                page.screenshot(path=str(OUT / "disconnected.png"))
                page.unroute("**/api/snapshot")
                page.locator("#reconnect").click()
                expect(page.locator("#status-banner")).to_have_class("status-banner live")
                checks.append("idle disconnect detection, retained stale observations and reconnect")

                # Explicit reconnect accepts state 0 from a restarted session.
                fresh = AluSession().snapshot()
                page.route("**/api/snapshot", lambda route: route.fulfill(json=fresh))
                page.locator("#reconnect").click()
                expect(y).to_have_text("0")
                expect(page.locator("#a-dec")).to_have_value("0")
                page.unroute("**/api/snapshot")
                page.locator("#reconnect").click()
                expect(y).to_have_text("7")
                checks.append("restart epoch via explicit reconnect")

                fault = AluSession()
                fault.ctx.set("net_b_add0", 1, stuck=True)
                fault.circuit.settle()
                mismatch = fault.snapshot()
                page.route("**/api/snapshot", lambda route: route.fulfill(json=mismatch))
                page.locator("#reconnect").click()
                expect(page.locator("#comparison-status")).to_contain_text("b_add")
                page.locator("#comparison-detail summary").click()
                expect(page.locator("#comparison-detail table")).to_be_visible()
                page.unroute("**/api/snapshot")
                fault.reset()
                fault.ctx.set("net_a0", 2)  # the engine's X wire value
                fault.circuit.settle()
                unknown = fault.snapshot()
                page.route("**/api/snapshot", lambda route: route.fulfill(json=unknown))
                page.locator("#reconnect").click()
                expect(y).to_have_text("—")
                expect(page.locator('[data-observe-bus="y"] .bus-binary')).to_contain_text("X")
                page.unroute("**/api/snapshot")
                page.locator("#reconnect").click()
                expect(y).to_have_text("7")
                checks.append("Python fault snapshots: first mismatch and X remain visible without zero coercion")

                # Final captures use actual server data, not an injected fixture.
                edit("#a-hex", "0F")
                edit("#b-dec", "1")
                page.locator("#clear-selection").click()
                page.locator('[data-trace="0"]').click()
                page.locator("#fit").click()
                for width, height in ((1440, 900), (1280, 800)):
                    page.set_viewport_size({"width": width, "height": height})
                    page.locator("#fit").click()
                    page.evaluate("window.scrollTo(0,0)")
                    page.screenshot(path=str(OUT / f"live-{width}x{height}.png"))
                    bounds = page.evaluate("""() => {
                      const view=document.querySelector('#map-viewport').getBoundingClientRect();
                      return [...document.querySelectorAll('.chip-body')].map(e=>{
                        const r=e.getBoundingClientRect(); return r.left>=view.left-1 && r.right<=view.right+1 && r.top>=view.top-1 && r.bottom<=view.bottom+1;
                      });
                    }""")
                    assert len(bounds) == 12 and all(bounds), (width, height, bounds)
                    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
                    readable = page.locator(".chip-title").evaluate_all("els => els.every(e => parseFloat(getComputedStyle(e).fontSize)*e.getScreenCTM().a >= 10)")
                    assert readable, (width, height, "default chip labels are too small")
                    assert page.locator(".map-panel").bounding_box()["y"] + page.locator(".map-panel").bounding_box()["height"] <= height + 1
                checks.append("1440x900 and 1280x800: twelve chips fit; no horizontal document overflow")
                assert not errors, errors
                browser.close()
        finally:
            server.shutdown()
            thread.join(timeout=3)
    (OUT / "browser-checks.json").write_text(json.dumps({"checks": checks, "page_errors": errors}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"passed": len(checks), "checks": checks, "artifacts": str(OUT)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    run()
