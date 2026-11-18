import json
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(
        channel="chrome",
        headless=False,
        args=["--disable-blink-features=AutomationControlled"],
        ignore_default_args=["--enable-automation"]
    )
    context = browser.new_context()
    page = context.new_page()
    page.goto("https://flow.google.com")
    input("\n>>> Brauzerda Google Flow akkauntingizga kiring. Kirib bo'lgach shu yerga qaytib ENTER bosing...")
    cookies = context.cookies()
    with open("flow_cookies.json", "w", encoding="utf-8") as f:
        json.dump(cookies, f, indent=2)
    print("Tayyor! flow_cookies.json saqlandi.")
    browser.close()
