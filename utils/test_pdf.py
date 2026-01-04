import asyncio

from playwright.async_api import async_playwright

URL = "https://oracc.museum.upenn.edu/saao/saa01/P224417/html"


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()

        await page.goto(URL, wait_until="networkidle")
        await page.emulate_media(media="print")

        # Часто помогает убрать фиксированные футеры/хедеры или элементы, мешающие разбиению
        await page.add_style_tag(
            content="""
            @page { margin: 14mm 12mm 18mm 12mm; }
            /* на случай фиксированных элементов */
            header, footer, .sticky, .fixed, nav { position: static !important; }
        """
        )

        await page.pdf(
            path="one.pdf",
            print_background=True,
            prefer_css_page_size=True,
            margin={"top": "14mm", "bottom": "18mm", "left": "12mm", "right": "12mm"},
            scale=0.98,
        )

        await browser.close()


asyncio.run(main())
