"""Demo 页面真实浏览器验证（playwright / chromium）"""
import sys
import time

from playwright.sync_api import sync_playwright

URL = "http://127.0.0.1:8916/"
OUT = r"D:\aivg193\evidence"


def main():
    with sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_page(viewport={"width": 1440, "height": 980})
        errs = []
        page.on("console", lambda m: errs.append(f"{m.type}: {m.text}") if m.type == "error" else None)
        page.on("pageerror", lambda e: errs.append(f"pageerror: {e}"))

        page.goto(URL, wait_until="networkidle")
        print("title:", page.title())
        print("health:", page.inner_text("#health"))
        print("pool:", page.inner_text("#pool")[:120].replace("\n", " / "))

        # 场景 1：t2v 默认
        page.fill("#prompt", "a paper crane unfolding into a real bird, studio light, cinematic")
        page.click("#go")
        page.wait_for_selector("#out video", timeout=300000)
        src = page.get_attribute("#out video", "src")
        print("t2v video:", src)
        print("meta:", page.inner_text("#meta").replace("\n", " | "))
        page.screenshot(path=OUT + r"\ui_t2v.png", full_page=False)

        # 场景 2：t2i
        page.select_option("#ep", "/t2i")
        page.fill("#prompt", "an isometric tiny greenhouse with glowing plants, digital art")
        page.click("#go")
        page.wait_for_selector("#out img", timeout=300000)
        print("t2i img:", page.get_attribute("#out img", "src"))
        print("meta:", page.inner_text("#meta").replace("\n", " | "))
        page.screenshot(path=OUT + r"\ui_t2i.png", full_page=False)

        # 场景 3：OpenAI chat 端点
        page.select_option("#ep", "/v1/chat/completions")
        page.fill("#prompt", "a tiny robot watering a bonsai tree, warm light")
        page.click("#go")
        page.wait_for_selector("#out video", timeout=300000)
        print("chat video:", page.get_attribute("#out video", "src"))
        page.screenshot(path=OUT + r"\ui_chat.png", full_page=False)

        print("console errors:", errs or "none")
        b.close()


if __name__ == "__main__":
    main()
