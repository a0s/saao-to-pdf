#!/usr/bin/env python3
"""
Генерация объединенного PDF с оглавлением из links_metadata.json
Обрабатывает первые 2 секции и создает единый PDF с навигацией
"""

import argparse
import asyncio
import json
import logging
import os
import re
import time
from asyncio import Semaphore
from concurrent.futures import ThreadPoolExecutor

from playwright.async_api import async_playwright
from playwright.sync_api import sync_playwright

# Импортируем стили и функции из print_with_fix.py
from print_with_fix import PRINT_FIX_CSS, inject_print_styles

# Настройка логирования
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Константы
METADATA_FILE = "links_metadata.json"
OUTPUT_PDF = "combined_saa_pdf.pdf"
INTERMEDIATE_HTML = "combined_document.html"  # Промежуточный HTML файл
TIMEOUT = 30000  # 30 секунд
MAX_SECTIONS = None  # None = обрабатывать все секции, или укажите число для ограничения (можно переопределить через --max-sections)
MAX_ITEMS_PER_SECTION = (
    None  # None = обрабатывать все элементы в секции, или укажите число для ограничения
)
NUM_WORKERS = 10  # Количество параллельных браузеров для обработки


def format_time(seconds):
    """Форматирует время в читаемый вид (чч:мм:сс или мм:сс)"""
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


async def process_items_async(tasks, total_items, start_time):
    """Async обработка всех элементов параллельно"""
    semaphore = Semaphore(NUM_WORKERS)
    processed = 0
    results = {}
    processed_lock = asyncio.Lock()

    async def process_task_async(task_data):
        """Обработка одной задачи async"""
        nonlocal processed
        position_key, item_url, item_name, is_first_item = task_data

        async with semaphore:
            async with async_playwright() as p_async:
                browser = await p_async.chromium.launch(headless=True)
                worker_page = await browser.new_page()
                try:
                    content = await process_item_page_async(
                        worker_page, item_url, item_name, is_first_item
                    )

                    # Обновляем прогресс
                    async with processed_lock:
                        processed += 1
                        elapsed_time = time.time() - start_time
                        if processed > 0:
                            avg_time_per_item = elapsed_time / processed
                            remaining_items = total_items - processed
                            estimated_remaining_time = (
                                avg_time_per_item * remaining_items
                            )

                            elapsed_str = format_time(elapsed_time)
                            remaining_str = format_time(estimated_remaining_time)

                            logger.info(
                                f"Прогресс: {processed}/{total_items} | "
                                f"Прошло: {elapsed_str} | "
                                f"Осталось ~{remaining_str} | "
                                f"Обработан: {item_name}"
                            )

                    if content:
                        results[position_key] = content
                finally:
                    await browser.close()

    # Запускаем все задачи параллельно
    await asyncio.gather(*[process_task_async(task) for task in tasks])
    return results


def load_metadata():
    """Загрузить метаданные из JSON"""
    if not os.path.exists(METADATA_FILE):
        logger.error(f"Файл {METADATA_FILE} не найден")
        return None

    try:
        with open(METADATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Ошибка при загрузке {METADATA_FILE}: {e}")
        return None


def extract_original_styles(page):
    """
    Извлечь оригинальные CSS стили из страницы
    Стили одинаковы для всех страниц, поэтому извлекаем один раз
    """
    logger.info("Извлечение оригинальных CSS стилей...")

    styles_html = page.evaluate(
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
    """Генерировать ID для якоря из текста"""
    # Убираем специальные символы, оставляем только буквы, цифры и дефисы
    anchor = text.lower()
    anchor = re.sub(r"[^a-z0-9]+", "-", anchor)
    anchor = re.sub(r"^-+|-+$", "", anchor)
    anchor = anchor[:50]  # Ограничиваем длину

    if prefix:
        return f"{prefix}-{anchor}" if anchor else prefix
    return anchor or "anchor"


def generate_toc_html(sections):
    """Создать HTML оглавления со стилями"""
    logger.info("Генерация оглавления...")

    toc_items = []

    for section_idx, section in enumerate(sections):
        section_name = section.get("section_name", "")
        section_anchor = f"section-{section_idx}"

        # Заголовок секции
        toc_items.append(
            f'    <h2 class="toc-section"><a href="#{section_anchor}">{section_name}     <span class="toc-page"></span></a></h2>'
        )
        toc_items.append('    <ul class="toc-items">')

        # Элементы секции
        for item in section.get("items", []):
            item_name = item.get("item_name", "")
            item_full_name = item.get("item_full_name", "")

            # Используем item_name для создания якоря
            item_anchor = generate_anchor_id(item_name, "item")

            # Используем item_full_name, заменяя табуляцию на пробелы
            display_name = (
                item_full_name.replace("\t", " ") if item_full_name else item_name
            )

            toc_items.append(
                f'      <li class="toc-item"><a href="#{item_anchor}"><span class="toc-text">{display_name}</span>     <span class="toc-page"></span></a></li>'
            )

        toc_items.append("    </ul>")

    toc_html = f"""
<div class="toc-container">
  <h1 class="toc-title">Table of Contents</h1>
{chr(10).join(toc_items)}
</div>
"""

    # CSS стили для оглавления
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
    """Async версия inject_print_styles - точная копия sync версии"""
    await page.add_style_tag(content=PRINT_FIX_CSS)

    # Подготовка страницы для печати через JavaScript (точная копия из print_with_fix.py)
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
        // Создаем ID из текста заголовка (для якоря)
        const anchorId = subtitleText.toLowerCase()
          .replace(/[^a-z0-9]+/g, '-')
          .replace(/^-+|-+$/g, '')
          .substring(0, 50);
        h3.id = anchorId || 'doc-subtitle';
        h3.textContent = subtitleText;
        headerContainer.appendChild(h3);
      }

      // Находим первую таблицу
      const tables = document.querySelectorAll('table');
      if (tables.length > 0) {
        const firstTable = tables[0];

        // Скрываем все предыдущие элементы
        let element = firstTable.previousElementSibling;
        while (element) {
          const prev = element.previousElementSibling;
          element.style.display = 'none';
          element = prev;
        }

        // Скрываем все элементы в родителе до таблицы
        let parent = firstTable.parentElement;
        while (parent && parent !== document.body) {
          let sibling = parent.previousElementSibling;
          while (sibling) {
            const prev = sibling.previousElementSibling;
            if (!sibling.contains(firstTable)) {
              sibling.style.display = 'none';
            }
            sibling = prev;
          }
          parent = parent.parentElement;
        }

        // Вставляем заголовки перед таблицей
        if (headerContainer.children.length > 0) {
          if (firstTable.parentElement === document.body) {
            firstTable.parentElement.insertBefore(headerContainer, firstTable);
          } else {
            // Если таблица не в body, перемещаем и таблицу, и заголовки
            const container = document.createElement('div');
            container.className = 'doc-content';
            container.appendChild(headerContainer);

            const clone = firstTable.cloneNode(true);
            container.appendChild(clone);

            document.body.insertBefore(container, document.body.firstChild);
            firstTable.style.display = 'none';
          }
        }
      } else {
        // Если таблицы нет, просто добавляем заголовки в начало body
        if (headerContainer.children.length > 0) {
          document.body.insertBefore(headerContainer, document.body.firstChild);
        }
      }

      // Скрываем оригинальные заголовки
      if (titleElement) titleElement.style.display = 'none';
      if (subtitleElement && subtitleElement.parentElement) {
        subtitleElement.parentElement.style.display = 'none';
      }

      // Убираем пустые элементы
      const allElements = document.querySelectorAll('div, p, section');
      allElements.forEach(el => {
        if (el && el.children.length === 0 && !el.textContent.trim()) {
          el.style.display = 'none';
        }
      });

      // Убираем горизонтальные линии
      document.querySelectorAll('hr').forEach(hr => hr.style.display = 'none');
    })();
    """
    await page.evaluate(prepare_script)


async def process_item_page_async(page, item_url, item_name, is_first_item=False):
    """Async версия process_item_page"""
    try:
        # Добавляем /html к URL если его нет
        if not item_url.endswith("/html"):
            item_url = item_url.rstrip("/") + "/html"

        logger.info(f"Обработка: {item_name} - {item_url}")

        # Загружаем страницу
        await page.goto(item_url, wait_until="networkidle", timeout=TIMEOUT)
        await page.wait_for_timeout(1000)

        # Применяем стили для печати
        await inject_print_styles_async(page)
        await page.wait_for_timeout(500)

        # Извлекаем обработанный контент (точная копия sync версии)
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

        # Добавляем якорь к заголовку h3
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

        # Обертываем в div с page-break
        if not is_first_item:
            content_html = f'<div class="item-content" style="page-break-before: always;">{content_html}</div>'
        else:
            content_html = f'<div class="item-content">{content_html}</div>'

        return content_html

    except Exception as e:
        logger.error(f"Ошибка при обработке {item_name}: {e}", exc_info=True)
        return None


def process_item_page(page, item_url, item_name, is_first_item=False):
    """
    Загрузить и обработать страницу элемента
    Возвращает обработанный HTML контент

    Args:
        page: Playwright page object
        item_url: URL страницы элемента
        item_name: Название элемента
        is_first_item: True если это первый элемент в документе
    """
    try:
        # Добавляем /html к URL если его нет
        if not item_url.endswith("/html"):
            item_url = item_url.rstrip("/") + "/html"

        logger.info(f"Обработка: {item_name} - {item_url}")

        # Загружаем страницу
        page.goto(item_url, wait_until="networkidle", timeout=TIMEOUT)
        page.wait_for_timeout(1000)  # Дополнительная пауза для загрузки

        # Применяем стили для печати
        inject_print_styles(page)
        page.wait_for_timeout(500)

        # Извлекаем обработанный контент
        content_html = page.evaluate(
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

        # Добавляем якорь к заголовку h3 (subtitle)
        # inject_print_styles уже создает id для h3, нужно его заменить на наш
        item_anchor = generate_anchor_id(item_name, "item")

        # Удаляем все существующие id из h3 и добавляем наш
        # Сначала удаляем все id атрибуты из h3
        content_html = re.sub(
            r'(<h3[^>]*?)(\s+id=["\'][^"\']*["\'])+',
            r"\1",
            content_html,
        )

        # Теперь добавляем наш id к h3 с классом doc-title-h3
        if (
            'class="doc-title-h3"' in content_html
            or "class='doc-title-h3'" in content_html
        ):
            # Заменяем, добавляя наш id
            content_html = re.sub(
                r'(<h3[^>]*class=["\']doc-title-h3["\'][^>]*)',
                f'\\1 id="{item_anchor}"',
                content_html,
                count=1,
            )
        elif "<h3" in content_html:
            # Если h3 есть, но без класса doc-title-h3, добавляем и класс и id
            content_html = re.sub(
                r"(<h3)([^>]*)(>)",
                f'\\1\\2 id="{item_anchor}" class="doc-title-h3"\\3',
                content_html,
                count=1,
            )
        else:
            # Если h3 нет вообще, добавляем якорь перед контентом
            content_html = (
                f'<h3 id="{item_anchor}" class="doc-title-h3"></h3>{content_html}'
            )

        # Убеждаемся, что id добавлен (проверяем без кавычек тоже)
        if (
            f'id="{item_anchor}"' not in content_html
            and f"id='{item_anchor}'" not in content_html
        ):
            logger.warning(
                f"Не удалось добавить якорь {item_anchor} для {item_name}, добавляю fallback"
            )
            # Добавляем якорь в начало контента как fallback
            content_html = (
                f'<div id="{item_anchor}" class="item-anchor"></div>{content_html}'
            )

        # Добавляем контейнер для элемента
        content_html = f'<div class="item-content">{content_html}</div>'

        logger.info(f"✅ Обработан: {item_name}")
        return content_html

    except Exception as e:
        logger.error(f"Ошибка при обработке {item_name}: {e}")
        return None


def combine_html_document(original_styles, toc_html, content_parts):
    """Объединить все части в единый HTML документ"""
    logger.info("Объединение HTML документа...")

    # Объединяем все части контента
    content_html = "\n".join([part for part in content_parts if part])

    # Создаем полный HTML документ
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


def print_combined_pdf(page, html_content, output_path, html_file_path=None):
    """Распечатать объединенный HTML в PDF используя существующую страницу"""
    logger.info(f"Генерация PDF: {output_path}")

    # Для больших файлов используем file:// URL вместо set_content
    if html_file_path and os.path.exists(html_file_path):
        file_size = os.path.getsize(html_file_path)
        logger.info(f"Загрузка HTML через file:// URL: {html_file_path}")
        logger.info(
            f"Размер HTML файла: {file_size / 1024 / 1024:.2f} MB ({file_size} байт)"
        )
        file_url = f"file://{os.path.abspath(html_file_path)}"
        page.goto(file_url, wait_until="domcontentloaded", timeout=120000)
    elif html_content:
        logger.info("Загрузка HTML через set_content")
        logger.info(
            f"Размер HTML для загрузки: {len(html_content) / 1024 / 1024:.2f} MB ({len(html_content)} байт)"
        )
        page.set_content(html_content, wait_until="domcontentloaded", timeout=120000)
    else:
        raise ValueError("Необходимо указать либо html_content, либо html_file_path")

    page.wait_for_timeout(
        5000
    )  # Даем больше времени на применение стилей и загрузку ресурсов

    # Вычисляем номера страниц для оглавления
    logger.info("Вычисление номеров страниц для оглавления...")
    result = page.evaluate(
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

    page.wait_for_timeout(500)  # Даем время на обновление

    # Печатаем в PDF
    page.pdf(
        path=output_path,
        format="A4",
        margin={"top": "1cm", "right": "0.8cm", "bottom": "1.5cm", "left": "0.8cm"},
        print_background=False,
        prefer_css_page_size=True,
    )

    logger.info(f"✅ PDF успешно сохранен: {output_path}")


def generate_pdf_from_html(html_file_path, output_pdf_path):
    """Генерирует PDF из сохраненного HTML файла"""
    logger.info(f"Генерация PDF из HTML файла: {html_file_path}")

    if not os.path.exists(html_file_path):
        logger.error(f"HTML файл не найден: {html_file_path}")
        return False

    file_size = os.path.getsize(html_file_path)
    logger.info(
        f"Размер HTML файла: {file_size / 1024 / 1024:.2f} MB ({file_size} байт)"
    )

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        try:
            # Передаем путь к файлу для загрузки через file:// URL
            print_combined_pdf(
                page, None, output_pdf_path, html_file_path=html_file_path
            )
            logger.info("✅ PDF успешно сгенерирован из HTML!")
            return True
        except Exception as e:
            logger.error(f"Ошибка при генерации PDF: {e}", exc_info=True)
            return False
        finally:
            browser.close()


def main():
    """Основная функция"""
    parser = argparse.ArgumentParser(
        description="Генерация объединенного PDF из links_metadata.json"
    )
    parser.add_argument(
        "--from-html",
        action="store_true",
        help="Пропустить фетчинг и сгенерировать PDF из сохраненного HTML файла",
    )
    parser.add_argument(
        "--html-file",
        default=INTERMEDIATE_HTML,
        help=f"Путь к HTML файлу (по умолчанию: {INTERMEDIATE_HTML})",
    )
    parser.add_argument(
        "--output",
        default=OUTPUT_PDF,
        help=f"Путь к выходному PDF файлу (по умолчанию: {OUTPUT_PDF})",
    )
    parser.add_argument(
        "--min-section",
        type=int,
        default=None,
        help="Индекс первой секции для обработки (0-based). Например, --min-section 263 для последних двух секций",
    )
    parser.add_argument(
        "--max-sections",
        type=int,
        default=None,
        help="Максимальное количество секций для обработки",
    )

    args = parser.parse_args()

    # Если указан флаг --from-html, пропускаем фетчинг
    if args.from_html:
        logger.info("Режим: генерация PDF из HTML (пропуск фетчинга)")
        generate_pdf_from_html(args.html_file, args.output)
        return

    logger.info("Начало генерации объединенного PDF")

    # Загружаем метаданные
    metadata = load_metadata()
    if not metadata:
        logger.error("Не удалось загрузить метаданные")
        return

    sections = metadata.get("sections", [])
    if not sections:
        logger.error("Нет секций в метаданных")
        return

    # Определяем, какие секции обрабатывать
    min_idx = args.min_section
    max_count = args.max_sections if args.max_sections is not None else MAX_SECTIONS

    if min_idx is not None:
        # Начинаем с указанного индекса
        if min_idx < 0:
            # Отрицательный индекс означает "с конца"
            min_idx = len(sections) + min_idx
        sections_to_process = sections[min_idx:]
        logger.info(f"Начинаем с секции {min_idx + 1} (индекс {min_idx})")
    else:
        sections_to_process = sections

    if max_count is not None:
        # Ограничиваем количество секций
        sections_to_process = sections_to_process[:max_count]

    logger.info(
        f"Обработка {len(sections_to_process)} секций (всего в файле: {len(sections)})"
    )

    if len(sections_to_process) == 0:
        logger.error("Нет секций для обработки")
        return

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        try:
            # Шаг 1: Извлекаем оригинальные стили из первой страницы
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

            logger.info(f"Загрузка образца страницы для извлечения стилей: {first_url}")
            page.goto(first_url, wait_until="networkidle", timeout=TIMEOUT)
            page.wait_for_timeout(1000)

            original_styles = extract_original_styles(page)

            # Шаг 2: Генерируем оглавление
            toc_html = generate_toc_html(sections_to_process)

            # Шаг 3: Обрабатываем все элементы параллельно
            # Сначала создаем заголовки секций
            section_headers = {}
            for section_idx, section in enumerate(sections_to_process):
                section_name = section.get("section_name", "")
                logger.info(f"Обработка секции {section_idx + 1}: {section_name}")

                # Добавляем якорь секции с заголовком
                section_anchor = f"section-{section_idx}"
                # Все секции кроме первой должны начинаться с новой страницы
                if section_idx > 0:
                    page_break = "page-break-before: always !important;"
                else:
                    page_break = "page-break-before: auto;"
                section_header = f'<div id="{section_anchor}" class="section-header" style="{page_break} margin-top: 2em; margin-bottom: 1em;"><h2 class="section-title">{section_name}</h2></div>'
                # Используем кортеж (section_idx, -1) для секций, чтобы они шли перед элементами
                section_headers[(section_idx, -1)] = section_header

            # Собираем все задачи для параллельной обработки
            tasks = []

            for section_idx, section in enumerate(sections_to_process):
                items = section.get("items", [])
                # Ограничиваем количество элементов если указано
                if MAX_ITEMS_PER_SECTION:
                    items_to_process = items[:MAX_ITEMS_PER_SECTION]
                else:
                    items_to_process = items

                for item_idx, item in enumerate(items_to_process):
                    item_name = item.get("item_name", "")
                    item_url = item.get("item_href", "")
                    is_first_item = section_idx == 0 and item_idx == 0

                    # Используем кортеж (section_idx, item_idx) для правильной сортировки
                    tasks.append(
                        ((section_idx, item_idx), item_url, item_name, is_first_item)
                    )

            total_items = len(tasks)
            logger.info(
                f"Запуск параллельной обработки {total_items} элементов с {NUM_WORKERS} воркерами"
            )

            # Запускаем async обработку в отдельном потоке
            start_time = time.time()

            def run_async():
                return asyncio.run(process_items_async(tasks, total_items, start_time))

            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(run_async)
                results = future.result()

            # Собираем финальный контент в правильном порядке
            final_content_parts = []
            for section_idx, section in enumerate(sections_to_process):
                # Добавляем заголовок секции
                final_content_parts.append(section_headers[(section_idx, -1)])

                # Добавляем элементы секции в правильном порядке
                items = section.get("items", [])
                if MAX_ITEMS_PER_SECTION:
                    items_to_process = items[:MAX_ITEMS_PER_SECTION]
                else:
                    items_to_process = items

                for item_idx in range(len(items_to_process)):
                    position_key = (section_idx, item_idx)
                    if position_key in results:
                        final_content_parts.append(results[position_key])

            # Шаг 4: Объединяем все в HTML
            combined_html = combine_html_document(
                original_styles, toc_html, final_content_parts
            )

            # Сохраняем промежуточный HTML для возможности повторной генерации PDF
            logger.info(f"Сохранение промежуточного HTML: {INTERMEDIATE_HTML}")
            html_size = len(combined_html)
            logger.info(
                f"Размер HTML: {html_size / 1024 / 1024:.2f} MB ({html_size} байт)"
            )
            with open(INTERMEDIATE_HTML, "w", encoding="utf-8") as f:
                f.write(combined_html)
            # Проверяем, что файл действительно записался
            saved_size = os.path.getsize(INTERMEDIATE_HTML)
            if saved_size != html_size:
                logger.warning(
                    f"⚠️ Размер сохраненного файла ({saved_size}) не совпадает с размером HTML ({html_size})"
                )
            else:
                logger.info(
                    f"✅ HTML сохранен: {INTERMEDIATE_HTML} ({saved_size / 1024 / 1024:.2f} MB)"
                )

            # Закрываем браузер после долгой обработки, чтобы избежать таймаутов
            browser.close()

            # Шаг 5: Генерируем PDF (создаем новый браузер)
            logger.info("Создание нового браузера для генерации PDF...")
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            # Передаем путь к HTML файлу для загрузки через file:// URL (более надежно для больших файлов)
            print_combined_pdf(
                page, combined_html, args.output, html_file_path=INTERMEDIATE_HTML
            )

            total_time = time.time() - start_time
            logger.info("✅ Генерация завершена успешно!")
            logger.info(f"⏱️  Общее время выполнения: {format_time(total_time)}")

        except Exception as e:
            logger.error(f"Критическая ошибка: {e}", exc_info=True)
        finally:
            browser.close()


if __name__ == "__main__":
    main()
