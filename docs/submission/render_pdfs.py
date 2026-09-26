"""Render the submission documents to A4 PDFs with Playwright Chromium.

    python docs/submission/render_pdfs.py            # both documents
    python docs/submission/render_pdfs.py business   # one document

Fonts: Poppins (headings) and Noto Sans CJK SC (body) give the intended look; other systems fall back to Segoe UI/Arial.
"""
import asyncio
import sys
from pathlib import Path
from playwright.async_api import async_playwright

HERE = Path(__file__).resolve().parent
DOCS = {
    'business': ('business-proposal.html', 'AlignSpace-Business-Proposal.pdf', 'Business Proposal'),
    'technical': ('technical-document.html', 'AlignSpace-Technical-Document.pdf', 'Technical Document'),
}


def footer(label):
    return ('<div style="width:100%;font:7pt Arial,sans-serif;color:#8a8ca0;padding:0 16mm;display:flex;justify-content:space-between">'
            f'<span>AlignSpace · {label} · Four Wolf Kings (8QFDUS2I)</span>'
            '<span><span class="pageNumber"></span> / <span class="totalPages"></span></span></div>')


async def main(names):
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        for name in names:
            source, target, label = DOCS[name]
            await page.goto((HERE / source).as_uri())
            await page.wait_for_load_state('networkidle')
            await page.evaluate('document.fonts.ready')
            await page.pdf(path=str(HERE / target), format='A4', print_background=True, prefer_css_page_size=True,
                           display_header_footer=True, header_template='<span></span>', footer_template=footer(label))
            print('wrote', target)
        await browser.close()

asyncio.run(main(sys.argv[1:] or list(DOCS)))
