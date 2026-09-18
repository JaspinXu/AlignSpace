"""Render docs/writeup/writeup.html to AlignSpace-writeup.pdf (A4) with Playwright Chromium.

    python docs/writeup/render_pdf.py

Edit the HTML (replace the highlighted <...> placeholders with the live URLs), then re-run.
"""
import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

HERE = Path(__file__).resolve().parent
FOOTER = ('<div style="width:100%;font-size:7pt;color:#888;text-align:center;font-family:sans-serif">'
          'AlignSpace · Four Wolf Kings (8QFDUS2I) · page <span class="pageNumber"></span> of <span class="totalPages"></span></div>')


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        await page.goto((HERE / 'writeup.html').as_uri())
        await page.wait_for_timeout(500)
        await page.pdf(path=str(HERE / 'AlignSpace-writeup.pdf'), format='A4', print_background=True,
                       prefer_css_page_size=True, display_header_footer=True,
                       header_template='<span></span>', footer_template=FOOTER)
        await browser.close()

asyncio.run(main())
