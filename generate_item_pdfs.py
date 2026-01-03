#!/usr/bin/env python3
"""
Скрипт для генерации отдельных PDF для каждого item из links_metadata.json
"""

import json
import os
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

# CSS стили для исправления обрезания текста при печати
PRINT_FIX_CSS = """
@media print {
  @page {
    margin: 1cm 0.8cm 1.5cm 0.8cm !important;
    size: A4;
  }

  body {
    margin: 0 !important;
    padding: 0 !important;
    overflow: visible !important;
  }

  /* Скрываем навигацию, но оставляем заголовки */
  header, nav, .header, .navigation, .breadcrumb,
  #p4MenuOutline, .p4MenuOutline, .menu, .sidebar {
    display: none !important;
  }

  /* Стили для заголовков документа */
  .doc-title-h2, .doc-title-h3 {
    page-break-after: avoid !important;
    page-break-inside: avoid !important;
    margin-top: 0.5em !important;
    margin-bottom: 0.3em !important;
    font-weight: bold !important;
  }

  .doc-title-h2 {
    font-size: 1.2em !important;
  }

  .doc-title-h3 {
    font-size: 1.1em !important;
  }

  /* Убираем лишние отступы сверху и пустые страницы */
  body > *:first-child {
    margin-top: 0 !important;
    padding-top: 0 !important;
    page-break-before: auto !important;
  }

  /* Начинаем с таблицы - убираем разрыв перед ней */
  table:first-of-type {
    page-break-before: auto !important;
    margin-top: 0 !important;
    padding-top: 0 !important;
  }

  /* Правильные переносы текста - предотвращение разрыва посреди буквы */
  * {
    word-break: break-word !important;
    overflow-wrap: break-word !important;
    hyphens: auto !important;
    -webkit-hyphens: auto !important;
    -moz-hyphens: auto !important;
    -ms-hyphens: auto !important;
  }

  /* Заголовки - не разрывать, но не создавать пустые страницы */
  h1, h2, h3, h4, h5, h6 {
    page-break-after: avoid !important;
    page-break-inside: avoid !important;
    page-break-before: auto !important;
    orphans: 3 !important;
    widows: 3 !important;
    margin-top: 0.5em !important;
    margin-bottom: 0.5em !important;
  }

  /* Таблицы - строгие правила против разрыва */
  table {
    page-break-inside: avoid !important;
    break-inside: avoid !important;
    page-break-before: auto !important;
    page-break-after: auto !important;
  }

  thead, tbody {
    page-break-inside: avoid !important;
    break-inside: avoid !important;
  }

  tr {
    page-break-inside: avoid !important;
    break-inside: avoid !important;
    page-break-after: avoid !important;
  }

  td, th {
    page-break-inside: avoid !important;
    break-inside: avoid !important;
    word-break: break-word !important;
    overflow-wrap: break-word !important;
  }

  /* Параграфы и блоки - правильные переносы, но не создавать пустые страницы */
  p, div, section, article {
    orphans: 3 !important;
    widows: 3 !important;
    page-break-inside: avoid !important;
    page-break-before: auto !important;
    word-break: break-word !important;
    overflow-wrap: break-word !important;
    margin-top: 0 !important;
    margin-bottom: 0.3em !important;
  }

  /* Убираем пустые div'ы и элементы */
  div:empty, p:empty {
    display: none !important;
  }

  /* Списки */
  ul, ol {
    page-break-inside: avoid !important;
    break-inside: avoid !important;
  }

  li {
    page-break-inside: avoid !important;
    break-inside: avoid !important;
    word-break: break-word !important;
    overflow-wrap: break-word !important;
  }

  /* Позиционирование */
  * {
    position: relative !important;
    overflow: visible !important;
  }

  body, html {
    min-height: auto !important;
    height: auto !important;
  }

  div, section, article {
    min-height: auto !important;
    max-height: none !important;
  }

  .content, main, #content, [role="main"] {
    padding-bottom: 2cm !important;
    margin-bottom: 1cm !important;
  }

  /* Скрытие навигации и лишних элементов */
  nav, header, footer, .navigation, .menu, .sidebar,
  .breadcrumb, #p4MenuOutline, .p4MenuOutline {
    display: none !important;
  }

  /* Убираем горизонтальные линии-разделители, которые могут создавать разрывы */
  hr {
    display: none !important;
    page-break-after: avoid !important;
  }

  /* Цвета для печати */
  * {
    color: #000 !important;
    background: transparent !important;
  }

  a {
    page-break-inside: avoid !important;
    word-break: break-word !important;
  }

  img {
    max-width: 100% !important;
    page-break-inside: avoid !important;
    break-inside: avoid !important;
  }

  pre, code, blockquote {
    page-break-inside: avoid !important;
    break-inside: avoid !important;
    white-space: pre-wrap !important;
    word-wrap: break-word !important;
    word-break: break-word !important;
    overflow-wrap: break-word !important;
  }

  /* Специальные правила для строк таблицы - не разрывать строки внутри ячеек */
  table td, table th {
    white-space: normal !important;
    word-wrap: break-word !important;
    word-break: break-word !important;
  }
}
"""


def inject_print_styles(page, title_text="", subtitle_text=""):
    """Инжектирует стили для печати в страницу с заданными заголовками"""
    page.add_style_tag(content=PRINT_FIX_CSS)

    # Экранируем текст для JavaScript
    title_js = json.dumps(title_text)
    subtitle_js = json.dumps(subtitle_text)

    # Подготовка страницы для печати через JavaScript
    prepare_script = f"""
    (function() {{
      // Скрываем навигацию и лишние элементы
      const elementsToHide = [
        'header', 'nav', '.header', '.navigation', '.breadcrumb',
        '#p4MenuOutline', '.p4MenuOutline', '.menu', '.sidebar'
      ];

      elementsToHide.forEach(selector => {{
        try {{
          const elements = document.querySelectorAll(selector);
          elements.forEach(el => {{
            if (el) el.style.display = 'none';
          }});
        }} catch(e) {{}}
      }});

      // Используем переданные заголовки
      let titleText = {title_js};
      let subtitleText = {subtitle_js};

      // Создаем контейнер для заголовков
      const headerContainer = document.createElement('div');
      headerContainer.className = 'doc-headers';
      headerContainer.style.marginBottom = '1em';

      // Создаем первый заголовок (h2) с якорем
      if (titleText) {{
        const h2 = document.createElement('h2');
        h2.className = 'doc-title-h2';
        h2.id = 'doc-title';
        h2.textContent = titleText;
        headerContainer.appendChild(h2);
      }}

      // Создаем второй заголовок (h3) с якорем
      if (subtitleText) {{
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
      }}

      // Находим первую таблицу
      const tables = document.querySelectorAll('table');
      if (tables.length > 0) {{
        const firstTable = tables[0];

        // Скрываем все предыдущие элементы
        let element = firstTable.previousElementSibling;
        while (element) {{
          const prev = element.previousElementSibling;
          element.style.display = 'none';
          element = prev;
        }}

        // Скрываем все элементы в родителе до таблицы
        let parent = firstTable.parentElement;
        while (parent && parent !== document.body) {{
          let sibling = parent.previousElementSibling;
          while (sibling) {{
            const prev = sibling.previousElementSibling;
            if (!sibling.contains(firstTable)) {{
              sibling.style.display = 'none';
            }}
            sibling = prev;
          }}
          parent = parent.parentElement;
        }}

        // Вставляем заголовки перед таблицей
        if (headerContainer.children.length > 0) {{
          if (firstTable.parentElement === document.body) {{
            firstTable.parentElement.insertBefore(headerContainer, firstTable);
          }} else {{
            // Если таблица не в body, перемещаем и таблицу, и заголовки
            const container = document.createElement('div');
            container.className = 'doc-content';
            container.appendChild(headerContainer);

            const clone = firstTable.cloneNode(true);
            container.appendChild(clone);

            document.body.insertBefore(container, document.body.firstChild);
            firstTable.style.display = 'none';
          }}
        }}
      }} else {{
        // Если таблицы нет, просто добавляем заголовки в начало body
        if (headerContainer.children.length > 0) {{
          document.body.insertBefore(headerContainer, document.body.firstChild);
        }}
      }}

      // Скрываем оригинальные заголовки
      const titleElement = document.querySelector('#p4HeadTitle');
      const subtitleElement = document.querySelector('h1.p3h2 > a, h1.p3h2');
      if (titleElement) titleElement.style.display = 'none';
      if (subtitleElement && subtitleElement.parentElement) {{
        subtitleElement.parentElement.style.display = 'none';
      }}

      // Убираем пустые элементы
      const allElements = document.querySelectorAll('div, p, section');
      allElements.forEach(el => {{
        if (el && el.children.length === 0 && !el.textContent.trim()) {{
          el.style.display = 'none';
        }}
      }});

      // Убираем горизонтальные линии
      document.querySelectorAll('hr').forEach(hr => hr.style.display = 'none');
    }})();
    """
    page.evaluate(prepare_script)


def print_item_to_pdf(url, output_path, title_text="", subtitle_text=""):
    """
    Печатает страницу item в PDF с заданными заголовками

    Args:
        url: URL страницы для печати
        output_path: Путь для сохранения PDF
        title_text: Текст заголовка (h2)
        subtitle_text: Текст подзаголовка (h3)
    """
    with sync_playwright() as p:
        # Запускаем браузер
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        print(f"  Загрузка страницы: {url}")
        page.goto(url, wait_until="networkidle")

        # Инжектируем стили с заголовками
        inject_print_styles(page, title_text, subtitle_text)

        # Ждем немного для применения стилей
        page.wait_for_timeout(500)

        print(f"  Печать в PDF: {output_path}")
        # Печатаем в PDF с настройками
        page.pdf(
            path=output_path,
            format="A4",
            margin={"top": "1cm", "right": "0.8cm", "bottom": "1.5cm", "left": "0.8cm"},
            print_background=False,
            prefer_css_page_size=True,
        )

        browser.close()


def sanitize_filename(filename):
    """Очищает имя файла от недопустимых символов"""
    # Заменяем недопустимые символы на подчеркивания
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        filename = filename.replace(char, '_')
    return filename


def process_items(metadata_file="links_metadata.json", output_dir="pdf-chunks", test_mode=True):
    """
    Обрабатывает items из links_metadata.json и генерирует PDF

    Args:
        metadata_file: Путь к файлу с метаданными
        output_dir: Папка для сохранения PDF
        test_mode: Если True, обрабатывает только первую секцию и первые 5 items
    """
    # Загружаем метаданные
    print(f"Загрузка метаданных из {metadata_file}...")
    with open(metadata_file, "r", encoding="utf-8") as f:
        metadata = json.load(f)

    # Создаем папку для PDF
    output_path = Path(output_dir)
    output_path.mkdir(exist_ok=True)
    print(f"Папка для PDF: {output_path.absolute()}")

    sections = metadata.get("sections", [])
    if not sections:
        print("❌ Нет секций в метаданных")
        return

    # Для теста обрабатываем только первую секцию
    sections_to_process = sections[:1] if test_mode else sections

    total_items = 0
    processed_items = 0

    for section_idx, section in enumerate(sections_to_process):
        section_name = section.get("section_name", f"Section {section_idx + 1}")
        items = section.get("items", [])

        print(f"\n{'='*60}")
        print(f"Секция {section_idx + 1}: {section_name}")
        print(f"Всего items в секции: {len(items)}")
        print(f"{'='*60}")

        # Для теста обрабатываем только первые 5 items
        items_to_process = items[:5] if test_mode else items

        for item_idx, item in enumerate(items_to_process):
            item_name = item.get("item_name", f"item_{item_idx + 1}")
            item_full_name = item.get("item_full_name", "")
            item_text = item.get("item_text", "")
            item_href = item.get("item_href", "")

            if not item_href:
                print(f"  ⚠️  Пропуск {item_name}: нет URL")
                continue

            # Обрабатываем заголовки: заменяем \t на пробелы
            title_text = item_full_name.replace("\t", " ").strip() if item_full_name else ""
            subtitle_text = item_text.replace("\t", " ").strip() if item_text else ""

            # Если title_text пустой, используем item_name
            if not title_text:
                title_text = item_name

            # Формируем имя файла: начинаем с item_name для натуральной сортировки
            safe_item_name = sanitize_filename(item_name)
            pdf_filename = f"{safe_item_name}.pdf"
            pdf_path = output_path / pdf_filename

            total_items += 1
            print(f"\n[{total_items}] Обработка: {item_name}")
            print(f"  Заголовок: {title_text}")
            if subtitle_text:
                print(f"  Подзаголовок: {subtitle_text}")
            print(f"  URL: {item_href}")

            try:
                print_item_to_pdf(item_href, str(pdf_path), title_text, subtitle_text)
                processed_items += 1
                print(f"  ✅ PDF сохранен: {pdf_path}")
            except Exception as e:
                print(f"  ❌ Ошибка при генерации PDF: {e}")
                continue

    print(f"\n{'='*60}")
    print(f"Обработка завершена!")
    print(f"Всего items: {total_items}")
    print(f"Успешно обработано: {processed_items}")
    print(f"Ошибок: {total_items - processed_items}")
    print(f"{'='*60}")


if __name__ == "__main__":
    test_mode = True
    if len(sys.argv) > 1 and sys.argv[1] == "--full":
        test_mode = False
        print("Режим полной обработки (все секции и все items)")
    else:
        print("Режим тестирования (первая секция, первые 5 items)")
        print("Для полной обработки используйте: python generate_item_pdfs.py --full")

    process_items(test_mode=test_mode)

