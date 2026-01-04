#!/usr/bin/env python3
"""
Генерация объединенного PDF с оглавлением из links_metadata.json
Обрабатывает первые 2 секции и создает единый PDF с навигацией
"""

import argparse
import json
import logging
import os
import re
import time

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
TIMEOUT = 30000  # 30 секунд
MAX_SECTIONS = None  # None = обрабатывать все секции, или укажите число для ограничения
MAX_ITEMS_PER_SECTION = (
    None  # None = обрабатывать все элементы в секции, или укажите число для ограничения
)


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


def generate_toc_html(sections, include_page_numbers=True):
    """Создать HTML оглавления со стилями

    Args:
        sections: Список секций для оглавления
        include_page_numbers: Если False, номера страниц не будут включены в HTML
    """
    logger.info("Генерация оглавления...")

    toc_items = []

    for section_idx, section in enumerate(sections):
        section_name = section.get("section_name", "")
        section_anchor = f"section-{section_idx}"

        # Заголовок секции
        if include_page_numbers:
            toc_items.append(
                f'    <h2 class="toc-section"><a href="#{section_anchor}">{section_name}     <span class="toc-page"></span></a></h2>'
            )
        else:
            toc_items.append(
                f'    <h2 class="toc-section"><a href="#{section_anchor}">{section_name}</a></h2>'
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

            if include_page_numbers:
                toc_items.append(
                    f'      <li class="toc-item"><a href="#{item_anchor}"><span class="toc-text">{display_name}</span>     <span class="toc-page"></span></a></li>'
                )
            else:
                toc_items.append(
                    f'      <li class="toc-item"><a href="#{item_anchor}"><span class="toc-text">{display_name}</span></a></li>'
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


def combine_html_document(original_styles, toc_html, content_parts, toc_only=False):
    """Объединить все части в единый HTML документ

    Args:
        original_styles: Оригинальные CSS стили (может быть пустой строкой для toc_only)
        toc_html: HTML оглавления
        content_parts: Список частей контента (может быть пустым для toc_only)
        toc_only: Если True, создает документ только с оглавлением
    """
    if toc_only:
        logger.info("Создание HTML документа только с оглавлением...")
        # Объединяем все части контента (для toc_only будет пусто)
        content_html = "\n".join([part for part in content_parts if part])

        # Минимальные стили для оглавления
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


def print_toc_only_pdf(page, html_content, output_path):
    """Распечатать только оглавление в PDF (без номеров страниц)"""
    logger.info(f"Генерация PDF только с оглавлением: {output_path}")

    # Загружаем HTML контент
    page.set_content(html_content, wait_until="networkidle")
    page.wait_for_timeout(2000)  # Даем время на применение стилей

    # Печатаем в PDF
    page.pdf(
        path=output_path,
        format="A4",
        margin={"top": "1cm", "right": "0.8cm", "bottom": "1.5cm", "left": "0.8cm"},
        print_background=False,
        prefer_css_page_size=True,
    )

    logger.info(f"✅ PDF с оглавлением успешно сохранен: {output_path}")


def print_combined_pdf(page, html_content, output_path):
    """Распечатать объединенный HTML в PDF используя существующую страницу"""
    logger.info(f"Генерация PDF: {output_path}")

    # Загружаем HTML контент
    page.set_content(html_content, wait_until="networkidle")
    page.wait_for_timeout(2000)  # Даем время на применение стилей

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


def parse_arguments():
    """Парсинг аргументов командной строки"""
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
        help="Путь к выходному PDF файлу (по умолчанию: table_of_content.pdf для --table-of-content-only, combined_saa_pdf.pdf для полного режима)",
    )
    return parser.parse_args()


def main():
    """Основная функция"""
    # Парсим аргументы командной строки
    args = parse_arguments()

    # Определяем дефолтные значения для выходных файлов
    if args.table_of_content_only:
        default_html = "table_of_content.html"
        default_pdf = "table_of_content.pdf"
        logger.info("Режим: генерация только оглавления")
    else:
        default_html = "combined_document.html"
        default_pdf = "combined_saa_pdf.pdf"
        logger.info("Начало генерации объединенного PDF")

    # Используем указанные значения или дефолтные
    output_html = args.target_html if args.target_html is not None else default_html
    output_pdf = args.target_pdf if args.target_pdf is not None else default_pdf

    # Загружаем метаданные
    metadata = load_metadata()
    if not metadata:
        logger.error("Не удалось загрузить метаданные")
        return

    sections = metadata.get("sections", [])
    if not sections:
        logger.error("Нет секций в метаданных")
        return

    # Ограничиваемся первыми MAX_SECTIONS секциями (если указано)
    if MAX_SECTIONS is None:
        sections_to_process = sections
    else:
        sections_to_process = sections[:MAX_SECTIONS]
    logger.info(
        f"Обработка {len(sections_to_process)} секций (всего в файле: {len(sections)})"
    )

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        try:
            if args.table_of_content_only:
                # Режим только оглавления
                # Шаг 1: Генерируем оглавление без номеров страниц
                toc_html = generate_toc_html(
                    sections_to_process, include_page_numbers=False
                )

                # Шаг 2: Создаем HTML документ только с оглавлением
                combined_html = combine_html_document(
                    original_styles="",
                    toc_html=toc_html,
                    content_parts=[],
                    toc_only=True,
                )

                # Шаг 3: Сохраняем HTML файл
                logger.info(f"Сохранение HTML: {output_html}")
                with open(output_html, "w", encoding="utf-8") as f:
                    f.write(combined_html)
                logger.info(f"✅ HTML файл сохранен: {output_html}")

                # Шаг 4: Генерируем PDF только с оглавлением
                print_toc_only_pdf(page, combined_html, output_pdf)

                logger.info("✅ Генерация оглавления завершена успешно!")
            else:
                # Обычный режим: полный PDF с контентом
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

                logger.info(
                    f"Загрузка образца страницы для извлечения стилей: {first_url}"
                )
                page.goto(first_url, wait_until="networkidle", timeout=TIMEOUT)
                page.wait_for_timeout(1000)

                original_styles = extract_original_styles(page)

                # Шаг 2: Генерируем оглавление
                toc_html = generate_toc_html(sections_to_process)

                # Шаг 3: Обрабатываем все элементы
                content_parts = []
                # Пересчитываем total_items с учетом ограничений
                if MAX_ITEMS_PER_SECTION:
                    total_items = sum(
                        min(len(s.get("items", [])), MAX_ITEMS_PER_SECTION)
                        for s in sections_to_process
                    )
                else:
                    total_items = sum(
                        len(s.get("items", [])) for s in sections_to_process
                    )
                processed = 0
                start_time = time.time()

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
                    content_parts.append(section_header)

                    items = section.get("items", [])
                    # Ограничиваем количество элементов если указано
                    if MAX_ITEMS_PER_SECTION:
                        items_to_process = items[:MAX_ITEMS_PER_SECTION]
                    else:
                        items_to_process = items

                    for item_idx, item in enumerate(items_to_process):
                        item_name = item.get("item_name", "")
                        item_url = item.get("item_href", "")

                        processed += 1

                        # Вычисляем время и оставшееся время
                        elapsed_time = time.time() - start_time
                        if processed > 0:
                            avg_time_per_item = elapsed_time / processed
                            remaining_items = total_items - processed
                            estimated_remaining_time = (
                                avg_time_per_item * remaining_items
                            )

                            # Форматируем время
                            elapsed_str = format_time(elapsed_time)
                            remaining_str = format_time(estimated_remaining_time)

                            logger.info(
                                f"Прогресс: {processed}/{total_items} | "
                                f"Прошло: {elapsed_str} | "
                                f"Осталось ~{remaining_str}"
                            )
                        else:
                            logger.info(f"Прогресс: {processed}/{total_items}")

                        # Первый элемент в первой секции не должен иметь разрыв страницы
                        is_first_item = section_idx == 0 and item_idx == 0
                        content = process_item_page(
                            page, item_url, item_name, is_first_item
                        )
                        if content:
                            content_parts.append(content)

                # Шаг 4: Объединяем все в HTML
                combined_html = combine_html_document(
                    original_styles, toc_html, content_parts
                )

                # Шаг 5: Сохраняем HTML файл
                logger.info(f"Сохранение HTML: {output_html}")
                with open(output_html, "w", encoding="utf-8") as f:
                    f.write(combined_html)
                logger.info(f"✅ HTML файл сохранен: {output_html}")

                # Шаг 6: Генерируем PDF (используем существующую страницу)
                print_combined_pdf(page, combined_html, output_pdf)

                total_time = time.time() - start_time
                logger.info("✅ Генерация завершена успешно!")
                logger.info(f"⏱️  Общее время выполнения: {format_time(total_time)}")

        except Exception as e:
            logger.error(f"Критическая ошибка: {e}", exc_info=True)
        finally:
            browser.close()


if __name__ == "__main__":
    main()
