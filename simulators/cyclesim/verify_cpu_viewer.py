"""Real Chromium acceptance checks for all three whole-CPU topologies.

python -m simulators.cyclesim.verify_cpu_viewer
No fitter or board is needed. Artifacts go to build/cpu-viewer-evidence.
"""
from __future__ import annotations

import json
from pathlib import Path
import threading

from playwright.sync_api import expect, sync_playwright

from simulators.cyclesim.cpu_viewer_model import cpu_circuit
from simulators.cyclesim.viewer_server import ViewerServer

OUT = Path(__file__).with_name("build") / "cpu-viewer-evidence"


def run():
    OUT.mkdir(parents=True, exist_ok=True)
    checks = []
    with ViewerServer(0) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch()
                try:
                    page = browser.new_page(viewport={"width": 1600, "height": 1100})
                    page.set_default_timeout(8000)
                    errors = []
                    page.on("pageerror", lambda error: errors.append(str(error)))
                    base = f"http://127.0.0.1:{server.server_port}"
                    page.goto(base + "/?view=cpu&variant=35")
                    expect(page.locator("#cpu-content")).to_be_visible()
                    expect(page.locator("#view-cpu")).to_have_attribute("aria-pressed", "true")
                    expect(page.locator(".controls")).to_be_hidden()
                    for variant in ("24", "29", "35"):
                        page.locator("#cpu-variant").select_option(variant)
                        expect(page.locator("#cpu-message")).to_contain_text(f"{variant}칩 ·")
                        expect(page.locator("#cpu-content")).to_be_visible()
                        expected = cpu_circuit(variant)
                        expect(page.locator(".cpu-chip")).to_have_count(int(variant))
                        expect(page.locator(".cpu-stat strong").nth(0)).to_have_text(variant)
                        expect(page.locator(".cpu-stat strong").nth(3)).to_have_text(str(expected["metrics"]["minimum_point_to_point_links"]))
                        for c in expected["components"]:
                            # Every chip has a real hit target, including all added PC parts.
                            expect(page.locator(f'#cpu-scene [data-cpu-id="{c["id"]}"]')).to_have_count(1)
                        expect(page.locator('#cpu-buses [data-cpu-id="DB"]')).to_have_attribute("aria-pressed", "true")
                        page.locator('#cpu-detail [data-cpu-id="DB[0]"]').click()
                        n = next(n for n in expected["nets"] if n["id"] == "DB[0]")
                        expect(page.locator("#cpu-detail [data-cpu-endpoint]")).to_have_count(len(n["endpoints"]))
                        for e in n["endpoints"]:
                            expect(page.locator(f'#cpu-detail [data-cpu-endpoint="{e["component"]}.{e["pin"]}"]')).to_have_count(1)
                        expect(page.locator(".cpu-chip.cpu-linked")).to_have_count(len({e["component"] for e in n["endpoints"]}))
                        with page.expect_download() as download:
                            page.locator("#cpu-download").click()
                        assert json.loads(Path(download.value.path()).read_text(encoding="utf-8")) == expected["board"]
                        page.locator('#cpu-buses [data-cpu-id="DB"]').click()
                        page.screenshot(path=str(OUT / f"cpu-{variant}-desktop.png"), full_page=True)
                    checks.append("24/29/35 chips, metrics, every DB[0] endpoint, highlighting, JSON exports")

                    # Final fit pads, NC outputs, and unambiguous PC vs PC_CARRY membership.
                    page.locator('#cpu-scene [data-cpu-id="edupccu"]').click()
                    expect(page.locator('#cpu-detail [data-cpu-pin="ir0"] .cpu-pad')).to_have_text("25")
                    page.locator('#cpu-detail [data-cpu-id="IR[0]"]').click()
                    expect(page.locator("#cpu-detail [data-cpu-endpoint]")).to_have_count(2)
                    page.locator('#cpu-scene [data-cpu-id="PC3"]').click()
                    expect(page.locator('#cpu-detail [data-cpu-pin="RCO"]')).to_contain_text("NC")
                    page.locator('#cpu-buses [data-cpu-id="PC"]').click()
                    expect(page.locator(".cpu-bit-list button")).to_have_count(16)
                    expect(page.locator(".cpu-bit-list")).not_to_contain_text("PC_CARRY")
                    page.locator('#cpu-detail [data-cpu-id="PC[15]"]').click()
                    expect(page.locator("#cpu-detail [data-cpu-endpoint]")).to_have_count(2)
                    checks.append("CPLD final pad 25, NC preserved, explicit ordered 16-bit PC bus")

                    page.locator("#cpu-search").fill("PC_CARRY[0]")
                    expect(page.locator("#cpu-results .cpu-result")).to_have_count(1)
                    page.locator("#cpu-results .cpu-result").click()
                    expect(page.locator("#cpu-detail [data-cpu-endpoint]")).to_have_count(2)
                    page.locator("#cpu-search").fill("missing-part")
                    expect(page.locator("#cpu-results")).to_contain_text("일치하는 칩이나 신호가 없습니다")
                    page.locator("#cpu-search").fill("74HC161")
                    expect(page.locator("#cpu-results .cpu-result")).to_have_count(5)
                    with page.expect_response(lambda response: response.url.endswith("/api/snapshot")):
                        page.locator("#cpu-search").focus()
                    expect(page.locator("#cpu-search")).to_be_focused()
                    expect(page.locator("#cpu-search")).to_have_value("74HC161")
                    expect(page.locator("#cpu-detail h3")).to_have_text("PC_CARRY[0]")
                    page.locator("#cpu-search").fill("")
                    page.locator("#cpu-filter").select_option("jtag")
                    expect(page.locator("#cpu-results .cpu-result")).to_have_count(8)
                    page.locator("#cpu-filter").select_option("all")
                    chip = page.locator('#cpu-scene [data-cpu-id="PC0"]')
                    chip.focus(); chip.press("Enter")
                    expect(page.locator("#cpu-detail h3")).to_have_text("PC0")
                    page.locator("#cpu-focus").click()
                    assert float(page.locator("#cpu-map").get_attribute("viewBox").split()[2]) < 1328
                    page.locator("#cpu-fit").click()
                    expect(page.locator("#cpu-map")).to_have_attribute("viewBox", "0 0 1328 800")
                    bounds = page.locator("#cpu-map").bounding_box()
                    page.mouse.move(bounds["x"]+4, bounds["y"]+4)
                    page.mouse.down()
                    page.mouse.move(bounds["x"]+64, bounds["y"]+34, steps=5)
                    page.mouse.up()
                    assert float(page.locator("#cpu-map").get_attribute("viewBox").split()[0]) < 0
                    page.locator("#cpu-fit").click()
                    page.locator("#cpu-zoom-in").click()
                    assert float(page.locator("#cpu-map").get_attribute("viewBox").split()[2]) < 1328
                    page.locator("#cpu-map").focus()
                    page.locator("#cpu-map").press("ArrowRight")
                    page.locator("#cpu-map").press("Home")
                    page.locator("#cpu-map").press("Escape")
                    expect(page.locator(".cpu-chip.cpu-selected")).to_have_count(0)
                    checks.append("search, filters, poll stability, keyboard selection, focus, drag pan, zoom, fit, clear")

                    # Exercise the sequence guard even if a transport ignores cancellation.
                    page.evaluate("""() => {
                      const original=window.fetch;
                      window.fetch=(url,options)=>String(url).includes('/api/cpu/circuit?variant=24')
                        ? original(url,{...options,signal:undefined}).then(r=>new Promise(resolve=>setTimeout(()=>resolve(r),400)))
                        : original(url,options);
                    }""")
                    page.locator("#cpu-variant").select_option("24")
                    page.locator("#cpu-variant").select_option("29")
                    expect(page.locator("#cpu-message")).to_contain_text("29칩 ·")
                    page.wait_for_timeout(600)  # Deliberately let the obsolete delayed response finish.
                    expect(page.locator(".cpu-chip")).to_have_count(29)
                    checks.append("late obsolete variant response cannot replace the current topology")

                    page.route("**/api/cpu/circuit?variant=35", lambda route: route.fulfill(
                        status=503, content_type="application/json", body=json.dumps({"error": "검증 자료 오류"})))
                    page.locator("#cpu-variant").select_option("35")
                    expect(page.locator("#cpu-message")).to_contain_text("검증 자료 오류")
                    expect(page.locator("#cpu-content")).to_be_hidden()
                    expect(page.locator("#cpu-retry")).to_be_visible()
                    page.unroute("**/api/cpu/circuit?variant=35")
                    page.locator("#cpu-retry").click()
                    expect(page.locator("#cpu-content")).to_be_visible()
                    expect(page.locator(".cpu-chip")).to_have_count(35)
                    checks.append("failed topology hides old counts and offers a working retry")

                    # ALU modes and CPU selection remain independent.
                    page.locator('#cpu-buses [data-cpu-id="ADDRESS"]').click()
                    page.locator("#view-assembly").click()
                    expect(page.locator("#cpu-view")).to_be_hidden()
                    expect(page.locator("#assembly-view")).to_be_visible()
                    page.locator("#view-cpu").click()
                    expect(page.locator("#cpu-detail h3")).to_have_text("ADDRESS[15:0]")
                    for width, height in ((1440,900), (1024,768), (390,844)):
                        page.set_viewport_size({"width": width, "height": height})
                        page.locator("#cpu-fit").click()
                        assert not page.evaluate("document.documentElement.scrollWidth>innerWidth"), f"overflow at {width}"
                        page.screenshot(path=str(OUT / f"cpu-35-{width}.png"), full_page=True)
                    page.reload()
                    expect(page.locator("#cpu-variant")).to_have_value("35")
                    expect(page.locator("#cpu-content")).to_be_visible()
                    checks.append("ALU mode separation, direct URL/reload, 1440/1024/390px layouts")
                    assert errors == [], errors
                    (OUT / "result.json").write_text(json.dumps(dict(status="passed", checks=checks, errors=errors),
                                                               ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
                finally:
                    browser.close()
        finally:
            server.shutdown()
            thread.join(timeout=3)
            assert not thread.is_alive()
    print(json.dumps(dict(status="passed", checks=checks, output=str(OUT)), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    run()
