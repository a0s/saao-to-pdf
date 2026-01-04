#!/usr/bin/env python3

import argparse
import asyncio
import json
import logging
import os
import re
import time

import requests
import urllib3
from playwright.async_api import async_playwright

from print_with_fix import PRINT_FIX_CSS

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

METADATA_FILE = "links_metadata.json"
OUTPUT_PDF = "combined_saa_pdf.pdf"
TIMEOUT = 30000
MAX_SECTIONS = None
MAX_ITEMS_PER_SECTION = None


def format_time(seconds):
    if seconds < 60:
        return f"{int(seconds)}с"
    elif seconds < 3600:
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{minutes}м {secs}с"
    else:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        return f"{hours}ч {minutes}м {secs}с"


def load_metadata():
    if not os.path.exists(METADATA_FILE):
        logger.error(f"Файл {METADATA_FILE} не найден")
        return None

    try:
        with open(METADATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Ошибка при загрузке {METADATA_FILE}: {e}")
        return None


async def extract_original_styles(page):
    logger.info("Извлечение оригинальных CSS стилей...")

    styles_html = await page.evaluate(
        """
    () => {
      let styles = '';

      // Извлекаем все <style> теги
      const styleTags = document.querySelectorAll('style');
      styleTags.forEach(tag => {
        styles += tag.outerHTML + '\\n';
      });

      // Извлекаем все <link rel="stylesheet"> теги
      const linkTags = document.querySelectorAll('link[rel="stylesheet"]');
      linkTags.forEach(tag => {
        styles += tag.outerHTML + '\\n';
      });

      return styles;
    }
    """
    )

    logger.info("✅ Оригинальные стили извлечены")
    return styles_html


def generate_anchor_id(text, prefix=""):
    anchor = text.lower()
    anchor = re.sub(r"[^a-z0-9]+", "-", anchor)
    anchor = re.sub(r"^-+|-+$", "", anchor)
    anchor = anchor[:50]

    if prefix:
        return f"{prefix}-{anchor}" if anchor else prefix
    return anchor or "anchor"


def generate_toc_html(sections, include_page_numbers=True):
    logger.info("Генерация оглавления...")

    toc_items = []

    for section_idx, section in enumerate(sections):
        section_name = section.get("section_name", "")
        section_anchor = f"section-{section_idx}"

        toc_items.append('    <div class="toc-section-wrapper">')

        if include_page_numbers:
            toc_items.append(
                f'      <h2 class="toc-section"><a href="#{section_anchor}">{section_name}     <span class="toc-page"></span></a></h2>'
            )
        else:
            toc_items.append(
                f'      <h2 class="toc-section"><a href="#{section_anchor}">{section_name}</a></h2>'
            )
        toc_items.append('      <ul class="toc-items">')

        for item in section.get("items", []):
            item_name = item.get("item_name", "")
            item_full_name = item.get("item_full_name", "")

            item_anchor = generate_anchor_id(item_name, "item")

            display_name = (
                item_full_name.replace("\t", " ") if item_full_name else item_name
            )

            if include_page_numbers:
                toc_items.append(
                    f'        <li class="toc-item"><a href="#{item_anchor}"><span class="toc-text">{display_name}</span>     <span class="toc-page"></span></a></li>'
                )
            else:
                toc_items.append(
                    f'        <li class="toc-item"><a href="#{item_anchor}"><span class="toc-text">{display_name}</span></a></li>'
                )

        toc_items.append("      </ul>")
        toc_items.append("    </div>")

    toc_html = f"""
<div class="toc-container">
  <h1 class="toc-title">Table of Contents</h1>
{chr(10).join(toc_items)}
</div>
"""

    toc_css = """
<style>
  .toc-container {
    page-break-after: always;
    margin-bottom: 2em;
  }

  .toc-title {
    font-size: 1.8em;
    font-weight: bold;
    margin-bottom: 1em;
    text-align: center;
    page-break-after: avoid;
  }

  .toc-section-wrapper {
    page-break-inside: avoid;
    margin-bottom: 0.5em;
  }

  .toc-section {
    font-size: 1.3em;
    font-weight: bold;
    margin-top: 1em;
    margin-bottom: 0.5em;
    page-break-after: avoid;
  }

  .toc-section a {
    color: #000;
    text-decoration: none;
    display: block;
    position: relative;
  }

  .toc-section a:hover {
    text-decoration: underline;
  }

  .toc-items {
    list-style-type: none;
    padding-left: 1.5em;
    margin-bottom: 1em;
  }

  .toc-item {
    margin-bottom: 0.3em;
    page-break-inside: avoid;
  }

  .toc-item a {
    color: #0066cc;
    text-decoration: none;
    display: block;
    position: relative;
    padding-right: 3em;
  }

  .toc-item a:hover {
    text-decoration: underline;
  }

  .toc-item a {
    display: block;
    position: relative;
  }

  .toc-text {
    display: inline;
  }

  .toc-page {
    float: right;
    color: #666;
    font-weight: normal;
    margin-left: 1em;
  }

  .toc-section a {
    display: block;
    position: relative;
  }

  .toc-section .toc-page {
    float: right;
    color: #666;
    font-weight: normal;
    margin-left: 1em;
  }

  /* Номера страниц будут добавлены через CSS при печати */

  @media print {
    .toc-container {
      page-break-after: always;
    }

    .toc-section-wrapper {
      page-break-inside: avoid;
      page-break-after: avoid;
    }

    .toc-section, .toc-item {
      page-break-inside: avoid;
    }

    .toc-section a,
    .toc-item a {
      color: #000;
    }

    .toc-item a {
      color: #0066cc;
    }

    /* Номера страниц для оглавления с точками-лидерами */
    .toc-item a .toc-page::after {
      content: leader('.') ' ' target-counter(attr(href), page);
    }

    .toc-section a .toc-page::after {
      content: ' ' target-counter(attr(href), page);
    }
  }
</style>
"""

    logger.info("✅ Оглавление сгенерировано")
    return toc_css + toc_html


async def inject_print_styles_async(page):
    await page.add_style_tag(content=PRINT_FIX_CSS)

    prepare_script = """
    (function() {
      // Скрываем навигацию и лишние элементы
      const elementsToHide = [
        'header', 'nav', '.header', '.navigation', '.breadcrumb',
        '#p4MenuOutline', '.p4MenuOutline', '.menu', '.sidebar'
      ];

      elementsToHide.forEach(selector => {
        try {
          const elements = document.querySelectorAll(selector);
          elements.forEach(el => {
            if (el) el.style.display = 'none';
          });
        } catch(e) {}
      });

      // Находим заголовки
      const titleElement = document.querySelector('#p4HeadTitle');
      const subtitleElement = document.querySelector('h1.p3h2 > a, h1.p3h2');

      // Извлекаем текст заголовков
      let titleText = '';
      let subtitleText = '';

      if (titleElement) {
        titleText = titleElement.textContent.trim();
      }

      if (subtitleElement) {
        subtitleText = subtitleElement.textContent.trim();
        // Убираем лишний текст типа [via saao/saa01] если есть
        subtitleText = subtitleText.replace(/\\s*\\[via[^\\]]+\\]\\s*/gi, '').trim();
      }

      // Создаем контейнер для заголовков
      const headerContainer = document.createElement('div');
      headerContainer.className = 'doc-headers';
      headerContainer.style.marginBottom = '1em';

      // Создаем первый заголовок (h2) с якорем
      if (titleText) {
        const h2 = document.createElement('h2');
        h2.className = 'doc-title-h2';
        h2.id = 'doc-title';
        h2.textContent = titleText;
        headerContainer.appendChild(h2);
      }

      // Создаем второй заголовок (h3) с якорем
      if (subtitleText) {
        const h3 = document.createElement('h3');
        h3.className = 'doc-title-h3';
        h3.id = 'doc-subtitle';
        h3.textContent = subtitleText;
        headerContainer.appendChild(h3);
      }

      // Вставляем контейнер в начало body
      if (headerContainer.children.length > 0) {
        const body = document.body;
        if (body.firstChild) {
          body.insertBefore(headerContainer, body.firstChild);
        } else {
          body.appendChild(headerContainer);
        }
      }
    })();
    """
    await page.evaluate(prepare_script)


async def process_item_page(page, item_url, item_name, is_first_item=False):
    try:
        if not item_url.endswith("/html"):
            item_url = item_url.rstrip("/") + "/html"

        logger.info(f"Обработка: {item_name} - {item_url}")

        await page.goto(item_url, wait_until="networkidle", timeout=TIMEOUT)
        await page.wait_for_timeout(1000)

        await inject_print_styles_async(page)
        await page.wait_for_timeout(500)

        content_html = await page.evaluate(
            """
        () => {
          // Находим контейнер с заголовками и таблицей
          const docContent = document.querySelector('.doc-content');
          const docHeaders = document.querySelector('.doc-headers');
          const tables = document.querySelectorAll('table');

          let html = '';

          // Если есть doc-content контейнер, извлекаем только h3 и таблицу (пропускаем h2)
          if (docContent) {
            // Извлекаем только h3 (subtitle), пропускаем h2 (title)
            const h3 = docContent.querySelector('h3.doc-title-h3');
            if (h3) {
              html += h3.outerHTML;
            }
            // Извлекаем таблицы из контейнера
            const containerTables = docContent.querySelectorAll('table');
            containerTables.forEach(table => {
              html += table.outerHTML;
            });
          } else {
            // Иначе собираем только h3 (subtitle) и таблицу, пропускаем h2 (title)
            if (docHeaders) {
              // Извлекаем только h3, пропускаем h2
              const h3 = docHeaders.querySelector('h3.doc-title-h3');
              if (h3) {
                html += h3.outerHTML;
              }
            }

            if (tables.length > 0) {
              tables.forEach(table => {
                html += table.outerHTML;
              });
            }
          }

          return html;
        }
        """
        )

        if not content_html:
            logger.warning(f"Не удалось извлечь контент для {item_name}")
            return None

        item_anchor = generate_anchor_id(item_name, "item")

        content_html = re.sub(
            r'(<h3[^>]*?)(\s+id=["\'][^"\']*["\'])+',
            r"\1",
            content_html,
        )

        if (
            'class="doc-title-h3"' in content_html
            or "class='doc-title-h3'" in content_html
        ):
            content_html = re.sub(
                r'(<h3[^>]*class=["\']doc-title-h3["\'][^>]*)',
                f'\\1 id="{item_anchor}"',
                content_html,
                count=1,
            )
        elif "<h3" in content_html:
            content_html = re.sub(
                r"(<h3)([^>]*)(>)",
                f'\\1\\2 id="{item_anchor}" class="doc-title-h3"\\3',
                content_html,
                count=1,
            )
        else:
            content_html = (
                f'<h3 id="{item_anchor}" class="doc-title-h3"></h3>{content_html}'
            )

        if (
            f'id="{item_anchor}"' not in content_html
            and f"id='{item_anchor}'" not in content_html
        ):
            logger.warning(
                f"Не удалось добавить якорь {item_anchor} для {item_name}, добавляю fallback"
            )
            content_html = (
                f'<div id="{item_anchor}" class="item-anchor"></div>{content_html}'
            )

        content_html = f'<div class="item-content">{content_html}</div>'

        logger.info(f"✅ Обработан: {item_name}")
        return content_html

    except Exception as e:
        logger.error(f"Ошибка при обработке {item_name}: {e}")
        return None


def combine_html_document(original_styles, toc_html, content_parts, toc_only=False):
    if toc_only:
        logger.info("Создание HTML документа только с оглавлением...")
        content_html = "\n".join([part for part in content_parts if part])

        full_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>SAA Table of Contents</title>

  <style>
  body {{
    font-family: Arial, sans-serif;
    line-height: 1.6;
    margin: 0;
    padding: 20px;
  }}

  .toc-container {{
    margin-bottom: 2em;
  }}

  .toc-title {{
    font-size: 1.8em;
    font-weight: bold;
    margin-bottom: 1em;
    text-align: center;
    page-break-after: avoid;
  }}

  .toc-section-wrapper {{
    page-break-inside: avoid;
    margin-bottom: 0.5em;
  }}

  .toc-section {{
    font-size: 1.3em;
    font-weight: bold;
    margin-top: 1em;
    margin-bottom: 0.5em;
    page-break-after: avoid;
  }}

  .toc-section a {{
    color: #000;
    text-decoration: none;
    display: block;
  }}

  .toc-items {{
    list-style-type: none;
    padding-left: 1.5em;
    margin-bottom: 1em;
  }}

  .toc-item {{
    margin-bottom: 0.3em;
    page-break-inside: avoid;
  }}

  .toc-item a {{
    color: #0066cc;
    text-decoration: none;
    display: block;
  }}

  .toc-text {{
    display: inline;
  }}

  @media print {{
    .toc-section-wrapper {{
      page-break-inside: avoid;
      page-break-after: avoid;
    }}

    .toc-section, .toc-item {{
      page-break-inside: avoid;
    }}

    .toc-section a,
    .toc-item a {{
      color: #000;
    }}

    .toc-item a {{
      color: #0066cc;
    }}
  }}
  </style>
</head>
<body>
  {toc_html}
  {content_html}
</body>
</html>
"""
        logger.info("✅ HTML документ с оглавлением создан")
        return full_html

    logger.info("Объединение HTML документа...")

    content_html = "\n".join([part for part in content_parts if part])

    full_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>SAA Combined Document</title>

  <!-- Оригинальные CSS стили из исходных страниц -->
  {original_styles}

  <!-- Стили для печати -->
  <style>
  {PRINT_FIX_CSS}

  /* Дополнительные стили для объединенного документа */
  @page {{
    counter-increment: page;
  }}

  body {{
    font-family: Arial, sans-serif;
    line-height: 1.6;
    counter-reset: page 1;
  }}

  .item-content {{
    margin-bottom: 2em;
    page-break-before: always;
  }}

  .item-content:first-of-type {{
    page-break-before: auto !important;
  }}

  .section-header {{
    page-break-after: avoid;
    page-break-inside: avoid;
    margin-top: 2em;
    margin-bottom: 1em;
  }}

  .section-header:not(:first-of-type) {{
    page-break-before: always !important;
  }}

  .section-title {{
    font-size: 1.5em;
    font-weight: bold;
    border-bottom: 2px solid #333;
    padding-bottom: 0.3em;
    page-break-after: avoid;
  }}
  </style>
</head>
<body>
  {toc_html}

  <div class="content">
    {content_html}
  </div>
</body>
</html>
"""

    logger.info("✅ HTML документ объединен")
    return full_html


async def print_toc_only_pdf(page, html_content, output_path):
    logger.info(f"Генерация PDF только с оглавлением: {output_path}")

    await page.set_content(html_content, wait_until="networkidle")
    await page.wait_for_timeout(2000)

    await page.pdf(
        path=output_path,
        format="A4",
        margin={"top": "1cm", "right": "0.8cm", "bottom": "1.5cm", "left": "0.8cm"},
        print_background=False,
        prefer_css_page_size=True,
    )

    logger.info(f"✅ PDF с оглавлением успешно сохранен: {output_path}")


async def inline_css_from_html_async(html_content, page):
    BASE_URL = "https://oracc.museum.upenn.edu"

    link_pattern = re.compile(
        r'<link\s+[^>]*rel=["\']stylesheet["\'][^>]*href=["\']([^"\']+)["\'][^>]*>',
        re.IGNORECASE,
    )

    def load_css(href):
        if href.startswith("/"):
            css_url = f"{BASE_URL}{href}"
        elif href.startswith("http"):
            css_url = href
        else:
            return None

        logger.info(f"Загрузка CSS: {css_url}")
        try:
            response = requests.get(css_url, verify=False, timeout=10)
            if response.status_code == 200:
                return response.text
            else:
                logger.warning(
                    f"Не удалось загрузить CSS {css_url}: статус {response.status_code}"
                )
                return None
        except Exception as e:
            logger.warning(f"Ошибка при загрузке CSS {css_url}: {e}")
            return None

    links = link_pattern.findall(html_content)

    css_contents = {}
    for href in links:
        css_content = await asyncio.to_thread(load_css, href)
        if css_content:
            css_contents[href] = css_content

    def replace_link(match):
        href = match.group(1)
        if href in css_contents:
            return f"<style>\n{css_contents[href]}\n</style>"
        return ""

    return link_pattern.sub(replace_link, html_content)


async def print_combined_pdf_from_file(page, html_file_path, output_path):
    logger.info(f"Генерация PDF из файла: {output_path}")

    logger.info(f"Чтение HTML из файла: {html_file_path}")
    with open(html_file_path, "r", encoding="utf-8") as f:
        html_content = f.read()

    logger.info("Встраивание внешних CSS в HTML...")
    html_content = await inline_css_from_html_async(html_content, page)

    logger.info("Загрузка HTML в браузер...")
    await page.set_content(html_content, wait_until="networkidle")
    await page.wait_for_timeout(2000)

    logger.info("Вычисление номеров страниц для оглавления...")
    result = await page.evaluate(
        """
    () => {
      const pageHeightPx = 1123;
      const marginTopPx = 38;
      const marginBottomPx = 57;
      const usablePageHeight = pageHeightPx - marginTopPx - marginBottomPx;

      const tocContainer = document.querySelector('.toc-container');
      const tocHeight = tocContainer ? tocContainer.offsetHeight : 0;

      const contentDiv = document.querySelector('.content');
      const contentStart = contentDiv ? contentDiv.offsetTop : tocHeight;

      const anchors = {};
      const allIds = [];

      const allElementsWithId = document.querySelectorAll('*[id]');
      allElementsWithId.forEach(el => {
        if (el.id) {
          allIds.push(el.id);
        }
      });

      allElementsWithId.forEach(el => {
        const id = el.id;
        if (id && (id.startsWith('section-') || id.startsWith('item-'))) {
          const style = window.getComputedStyle(el);
          if (style.display === 'none' || style.visibility === 'hidden') {
            return;
          }

          const rect = el.getBoundingClientRect();
          if (rect.height === 0 && rect.width === 0) {
            return;
          }

          const scrollTop = window.pageYOffset || document.documentElement.scrollTop;
          const absoluteTop = rect.top + scrollTop;

          const positionFromContentStart = absoluteTop - contentStart;

          let pageNum = 2;
          if (positionFromContentStart > 0) {
            pageNum = 2 + Math.floor(positionFromContentStart / usablePageHeight);
          } else if (positionFromContentStart <= 0 && absoluteTop < contentStart) {
            pageNum = 1;
          }

          anchors[id] = pageNum;
        }
      });

      let updatedCount = 0;
      let notFoundCount = 0;
      const notFoundAnchors = [];

      document.querySelectorAll('.toc-page').forEach(span => {
        const link = span.closest('a');
        if (link) {
          const href = link.getAttribute('href');
          if (href && href.startsWith('#')) {
            const anchorId = href.substring(1);
            const pageNum = anchors[anchorId];
            if (pageNum) {
              span.textContent = pageNum;
              span.style.display = 'inline';
              span.style.visibility = 'visible';
              updatedCount++;
            } else {
              notFoundAnchors.push(anchorId);
              notFoundCount++;
              span.textContent = '';
              span.style.display = 'none';
            }
          }
        }
      });

      if (notFoundAnchors.length > 0) {
        console.warn('Не найдены якоря:', notFoundAnchors.slice(0, 5));
      }
      return {
        totalAnchors: Object.keys(anchors).length,
        updated: updatedCount,
        notFound: notFoundCount,
        notFoundAnchors: notFoundAnchors.slice(0, 10),
        foundAnchors: Object.keys(anchors).slice(0, 10),
        allIds: allIds.filter(id => id.startsWith('item-') || id.startsWith('section-')).slice(0, 10)
      };
    }
    """
    )

    if result:
        logger.info(
            f"Найдено якорей: {result.get('totalAnchors', 0)}, обновлено номеров страниц: {result.get('updated', 0)}"
        )
        if result.get("notFound", 0) > 0:
            logger.warning(
                f"Не найдено якорей для {result.get('notFound', 0)} элементов (возможно, они не обрабатываются)"
            )

    await page.wait_for_timeout(500)

    await page.pdf(
        path=output_path,
        format="A4",
        margin={"top": "1cm", "right": "0.8cm", "bottom": "1.5cm", "left": "0.8cm"},
        print_background=False,
        prefer_css_page_size=True,
    )

    logger.info(f"✅ PDF успешно сохранен: {output_path}")


async def print_combined_pdf(page, html_content, output_path):
    logger.info(f"Генерация PDF: {output_path}")

    await page.set_content(html_content, wait_until="networkidle")
    await page.wait_for_timeout(2000)

    logger.info("Вычисление номеров страниц для оглавления...")
    result = await page.evaluate(
        """
    () => {
      // Эмулируем размеры страницы A4 при печати
      // A4: 210mm x 297mm
      // При 96 DPI: 794px x 1123px
      // С учетом отступов: top 1cm (38px), bottom 1.5cm (57px)
      const pageHeightPx = 1123; // Высота A4 в пикселях
      const marginTopPx = 38; // 1cm
      const marginBottomPx = 57; // 1.5cm
      const usablePageHeight = pageHeightPx - marginTopPx - marginBottomPx;

      // Получаем высоту оглавления
      const tocContainer = document.querySelector('.toc-container');
      const tocHeight = tocContainer ? tocContainer.offsetHeight : 0;

      // Находим начало контента (после оглавления)
      const contentDiv = document.querySelector('.content');
      const contentStart = contentDiv ? contentDiv.offsetTop : tocHeight;

      // Находим все якоря в документе
      const anchors = {};
      const allIds = [];

      // Ищем все элементы с ID - используем более широкий поиск
      const allElementsWithId = document.querySelectorAll('*[id]');
      allElementsWithId.forEach(el => {
        if (el.id) {
          allIds.push(el.id);
        }
      });

      // Ищем элементы с ID, начинающимся с section- или item-
      // Используем более широкий поиск, включая элементы внутри div.item-content
      allElementsWithId.forEach(el => {
        const id = el.id;
        // Проверяем, что это якорь секции или элемента
        if (id && (id.startsWith('section-') || id.startsWith('item-'))) {
          // Пропускаем элементы, которые скрыты
          const style = window.getComputedStyle(el);
          if (style.display === 'none' || style.visibility === 'hidden') {
            return;
          }

          const rect = el.getBoundingClientRect();
          // Пропускаем элементы с нулевой высотой (не отрендерены)
          if (rect.height === 0 && rect.width === 0) {
            return;
          }

          const scrollTop = window.pageYOffset || document.documentElement.scrollTop;
          const absoluteTop = rect.top + scrollTop;

          // Вычисляем позицию относительно начала контента
          const positionFromContentStart = absoluteTop - contentStart;

          // Номер страницы: оглавление на странице 1, контент начинается со страницы 2
          let pageNum = 2;
          if (positionFromContentStart > 0) {
            // Добавляем 1, так как контент начинается со страницы 2
            pageNum = 2 + Math.floor(positionFromContentStart / usablePageHeight);
          } else if (positionFromContentStart <= 0 && absoluteTop < contentStart) {
            // Если элемент находится в оглавлении
            pageNum = 1;
          }

          anchors[id] = pageNum;
        }
      });

      // Обновляем номера страниц в оглавлении
      let updatedCount = 0;
      let notFoundCount = 0;
      const notFoundAnchors = [];

      document.querySelectorAll('.toc-page').forEach(span => {
        const link = span.closest('a');
        if (link) {
          const href = link.getAttribute('href');
          if (href && href.startsWith('#')) {
            const anchorId = href.substring(1);
            const pageNum = anchors[anchorId];
            if (pageNum) {
              span.textContent = pageNum;
              span.style.display = 'inline';
              span.style.visibility = 'visible';
              updatedCount++;
            } else {
              notFoundAnchors.push(anchorId);
              notFoundCount++;
              span.textContent = '';
              span.style.display = 'none';
            }
          }
        }
      });


      // Логируем результаты
      if (notFoundAnchors.length > 0) {
        console.warn('Не найдены якоря:', notFoundAnchors.slice(0, 5));
      }
      // Возвращаем результаты для логирования
      return {
        totalAnchors: Object.keys(anchors).length,
        updated: updatedCount,
        notFound: notFoundCount,
        notFoundAnchors: notFoundAnchors.slice(0, 10),
        foundAnchors: Object.keys(anchors).slice(0, 10),
        allIds: allIds.filter(id => id.startsWith('item-') || id.startsWith('section-')).slice(0, 10)
      };
    }
    """
    )

    if result:
        logger.info(
            f"Найдено якорей: {result.get('totalAnchors', 0)}, обновлено номеров страниц: {result.get('updated', 0)}"
        )
        if result.get("notFound", 0) > 0:
            logger.warning(
                f"Не найдено якорей для {result.get('notFound', 0)} элементов (возможно, они не обрабатываются)"
            )

    await page.wait_for_timeout(500)

    await page.pdf(
        path=output_path,
        format="A4",
        margin={"top": "1cm", "right": "0.8cm", "bottom": "1.5cm", "left": "0.8cm"},
        print_background=False,
        prefer_css_page_size=True,
    )

    logger.info(f"✅ PDF успешно сохранен: {output_path}")


async def process_items_parallel(playwright_instance, tasks, worker_count=10):
    logger.info(f"Запуск параллельной обработки с {worker_count} воркерами...")

    semaphore = asyncio.Semaphore(worker_count)
    results = {}
    start_time = time.time()
    total_tasks = len(tasks)
    completed = 0
    completed_lock = asyncio.Lock()

    async def process_task(task_data):
        nonlocal completed
        index, item_url, item_name, is_first_item = task_data

        async with semaphore:
            browser = await playwright_instance.chromium.launch(headless=True)
            try:
                page = await browser.new_page()
                try:
                    content = await process_item_page(
                        page, item_url, item_name, is_first_item
                    )
                finally:
                    await page.close()
            finally:
                await browser.close()

            async with completed_lock:
                completed += 1
                elapsed_time = time.time() - start_time
                if completed > 0:
                    avg_time_per_item = elapsed_time / completed
                    remaining_items = total_tasks - completed
                    estimated_remaining_time = avg_time_per_item * remaining_items

                    elapsed_str = format_time(elapsed_time)
                    remaining_str = format_time(estimated_remaining_time)

                    logger.info(
                        f"Прогресс: {completed}/{total_tasks} | "
                        f"Прошло: {elapsed_str} | "
                        f"Осталось ~{remaining_str}"
                    )

            return (index, content)

    try:
        coroutines = [process_task(task) for task in tasks]
        task_results = await asyncio.gather(*coroutines, return_exceptions=True)

        for result in task_results:
            if isinstance(result, Exception):
                logger.error(f"Ошибка при обработке задачи: {result}")
                continue
            index, content = result
            results[index] = content
    except Exception as e:
        logger.error(f"Критическая ошибка при параллельной обработке: {e}")

    sorted_results = [results.get(i, None) for i in range(len(tasks))]
    logger.info(f"✅ Параллельная обработка завершена: {total_tasks} элементов")

    return sorted_results


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Генерация объединенного PDF с оглавлением из links_metadata.json"
    )
    parser.add_argument(
        "--table-of-content-only",
        action="store_true",
        help="Генерировать PDF только с оглавлением (без номеров страниц и контента)",
    )
    parser.add_argument(
        "--target-html",
        type=str,
        default=None,
        help="Путь к выходному HTML файлу (по умолчанию: table_of_content.html для --table-of-content-only, combined_document.html для полного режима)",
    )
    parser.add_argument(
        "--target-pdf",
        type=str,
        default=None,
        help="Путь к выходному PDF файлу (по умолчанию: table_of_content.pdf для --table-of-content-only, combined_document.pdf для полного режима)",
    )
    parser.add_argument(
        "--section-start",
        type=int,
        default=0,
        help="Индекс начальной секции для обработки (по умолчанию: 0). Может быть отрицательным для отсчета с конца (например: -3 означает 3 секции с конца)",
    )
    parser.add_argument(
        "--section-count",
        type=int,
        default=None,
        help="Количество секций для обработки (по умолчанию: все секции от section-start до конца)",
    )
    parser.add_argument(
        "--worker-count",
        type=int,
        default=20,
        help="Количество параллельных воркеров (браузеров) для обработки страниц (по умолчанию: 10)",
    )
    parser.add_argument(
        "--html-to-pdf-only",
        action="store_true",
        help="Только конвертировать существующий HTML файл в PDF (без генерации HTML)",
    )
    parser.add_argument(
        "--source-html",
        type=str,
        default="combined_document.html",
        help="Путь к исходному HTML файлу для конвертации в PDF (по умолчанию: combined_document.html). Используется только с --html-to-pdf-only",
    )
    return parser.parse_args()


async def main_async():
    args = parse_arguments()

    if args.html_to_pdf_only:
        source_html = args.source_html
        if not os.path.exists(source_html):
            logger.error(f"Исходный HTML файл не найден: {source_html}")
            return

        default_pdf = "combined_document.pdf"
        output_pdf = args.target_pdf if args.target_pdf is not None else default_pdf

        logger.info("Режим: конвертация HTML в PDF")
        logger.info(f"Исходный HTML: {source_html}")
        logger.info(f"Выходной PDF: {output_pdf}")

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()

            try:
                await print_combined_pdf_from_file(page, source_html, output_pdf)
                logger.info("✅ Конвертация HTML в PDF завершена успешно!")
            except Exception as e:
                logger.error(f"Критическая ошибка при конвертации: {e}", exc_info=True)
            finally:
                await browser.close()

        return

    if args.table_of_content_only:
        default_html = "table_of_content.html"
        default_pdf = "table_of_content.pdf"
        logger.info("Режим: генерация только оглавления")
    else:
        default_html = "combined_document.html"
        default_pdf = "combined_document.pdf"
        logger.info("Начало генерации объединенного PDF")

    output_html = args.target_html if args.target_html is not None else default_html
    output_pdf = args.target_pdf if args.target_pdf is not None else default_pdf

    metadata = load_metadata()
    if not metadata:
        logger.error("Не удалось загрузить метаданные")
        return

    sections = metadata.get("sections", [])
    if not sections:
        logger.error("Нет секций в метаданных")
        return

    section_start = args.section_start
    total_sections = len(sections)

    if section_start < 0:
        section_start = total_sections + section_start
        if section_start < 0:
            section_start = 0
            logger.warning(
                f"Индекс {args.section_start} выходит за границы, начинаем с 0"
            )

    if section_start >= total_sections:
        logger.error(
            f"Индекс начальной секции {section_start} выходит за границы (всего секций: {total_sections})"
        )
        return

    if args.section_count is not None:
        section_count = args.section_count
        if section_count <= 0:
            logger.error("Количество секций должно быть положительным числом")
            return
        section_end = min(section_start + section_count, total_sections)
    else:
        section_end = total_sections

    sections_to_process = sections[section_start:section_end]

    logger.info(
        f"Обработка секций {section_start}-{section_end-1} ({len(sections_to_process)} секций из {total_sections} всего)"
    )

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        try:
            if args.table_of_content_only:
                toc_html = generate_toc_html(
                    sections_to_process, include_page_numbers=False
                )

                combined_html = combine_html_document(
                    original_styles="",
                    toc_html=toc_html,
                    content_parts=[],
                    toc_only=True,
                )

                logger.info(f"Сохранение HTML: {output_html}")
                with open(output_html, "w", encoding="utf-8") as f:
                    f.write(combined_html)
                logger.info(f"✅ HTML файл сохранен: {output_html}")

                await print_toc_only_pdf(page, combined_html, output_pdf)

                logger.info("✅ Генерация оглавления завершена успешно!")
            else:
                first_item = None
                for section in sections_to_process:
                    items = section.get("items", [])
                    if items:
                        first_item = items[0]
                        break

                if not first_item:
                    logger.error("Не найдено элементов для обработки")
                    return

                first_url = first_item.get("item_href", "")
                if not first_url.endswith("/html"):
                    first_url = first_url.rstrip("/") + "/html"

                logger.info(
                    f"Загрузка образца страницы для извлечения стилей: {first_url}"
                )
                await page.goto(first_url, wait_until="networkidle", timeout=TIMEOUT)
                await page.wait_for_timeout(1000)

                original_styles = await extract_original_styles(page)

                toc_html = generate_toc_html(sections_to_process)

                tasks = []
                section_headers = []

                task_index = 0
                for section_idx, section in enumerate(sections_to_process):
                    section_name = section.get("section_name", "")
                    logger.info(f"Подготовка секции {section_idx + 1}: {section_name}")

                    section_anchor = f"section-{section_idx}"
                    if section_idx > 0:
                        page_break = "page-break-before: always !important;"
                    else:
                        page_break = "page-break-before: auto;"
                    section_header = f'<div id="{section_anchor}" class="section-header" style="{page_break} margin-top: 2em; margin-bottom: 1em;"><h2 class="section-title">{section_name}</h2></div>'
                    section_headers.append((section_idx, section_header))

                    items = section.get("items", [])
                    if MAX_ITEMS_PER_SECTION:
                        items_to_process = items[:MAX_ITEMS_PER_SECTION]
                    else:
                        items_to_process = items

                    for item_idx, item in enumerate(items_to_process):
                        item_name = item.get("item_name", "")
                        item_url = item.get("item_href", "")

                        is_first_item = section_idx == 0 and item_idx == 0

                        tasks.append((task_index, item_url, item_name, is_first_item))
                        task_index += 1

                start_time = time.time()
                logger.info(
                    f"Начинаем параллельную обработку {len(tasks)} элементов..."
                )

                item_contents = await process_items_parallel(
                    p, tasks, args.worker_count
                )

                content_parts = []

                current_task_index = 0
                for section_idx, section in enumerate(sections_to_process):
                    section_headers_dict = dict(section_headers)
                    if section_idx in section_headers_dict:
                        content_parts.append(section_headers_dict[section_idx])

                    items = section.get("items", [])
                    if MAX_ITEMS_PER_SECTION:
                        items_to_process = items[:MAX_ITEMS_PER_SECTION]
                    else:
                        items_to_process = items

                    for item_idx, item in enumerate(items_to_process):
                        if current_task_index < len(item_contents):
                            content = item_contents[current_task_index]
                            if content:
                                content_parts.append(content)
                            current_task_index += 1

                combined_html = combine_html_document(
                    original_styles, toc_html, content_parts
                )

                logger.info(f"Сохранение HTML: {output_html}")
                with open(output_html, "w", encoding="utf-8") as f:
                    f.write(combined_html)
                logger.info(f"✅ HTML файл сохранен: {output_html}")

                await print_combined_pdf(page, combined_html, output_pdf)

                total_time = time.time() - start_time
                logger.info("✅ Генерация завершена успешно!")
                logger.info(f"⏱️  Общее время выполнения: {format_time(total_time)}")

        except Exception as e:
            logger.error(f"Критическая ошибка: {e}", exc_info=True)
        finally:
            await browser.close()


def main():
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
