#!/usr/bin/env python3
"""
Скрипт для печати страницы Oracc в PDF с исправлением обрезания текста
"""

from playwright.sync_api import sync_playwright
import sys
import os

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

  /* Скрываем заголовки и навигацию полностью */
  header, nav, .header, .navigation, .breadcrumb,
  #p4MenuOutline, .p4MenuOutline, .menu, .sidebar,
  h1:first-of-type, h2:first-of-type,
  body > div:first-child, body > section:first-child {
    display: none !important;
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


def inject_print_styles(page):
    """Инжектирует стили для печати в страницу"""
    page.add_style_tag(content=PRINT_FIX_CSS)

    # Скрываем лишние элементы через JavaScript
    hide_script = """
    (function() {
      // Скрываем навигацию, заголовки и лишние элементы
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

      // Находим первую таблицу и скрываем все элементы до неё
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

        // Перемещаем таблицу в начало body для правильной печати
        if (firstTable.parentElement !== document.body) {
          const clone = firstTable.cloneNode(true);
          document.body.insertBefore(clone, document.body.firstChild);
          firstTable.style.display = 'none';
        }
      }

      // Скрываем все заголовки h1, h2 в начале документа
      const headings = document.querySelectorAll('h1, h2');
      headings.forEach((h, index) => {
        // Скрываем первые 2 заголовка (обычно это навигация)
        if (index < 2) {
          h.style.display = 'none';
        }
      });

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
    page.evaluate(hide_script)
    print("✅ Стили для печати успешно добавлены")


def print_to_pdf(url, output_path=None):
    """
    Печатает страницу в PDF с исправлением обрезания текста

    Args:
        url: URL страницы для печати
        output_path: Путь для сохранения PDF (по умолчанию: page.pdf)
    """
    if output_path is None:
        output_path = "page.pdf"

    with sync_playwright() as p:
        # Запускаем браузер
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        print(f"Загрузка страницы: {url}")
        page.goto(url, wait_until="networkidle")

        # Инжектируем стили
        inject_print_styles(page)

        # Ждем немного для применения стилей
        page.wait_for_timeout(500)

        print(f"Печать в PDF: {output_path}")
        # Печатаем в PDF с настройками
        page.pdf(
            path=output_path,
            format="A4",
            margin={
                "top": "1cm",
                "right": "0.8cm",
                "bottom": "1.5cm",
                "left": "0.8cm"
            },
            print_background=False,
            prefer_css_page_size=True
        )

        browser.close()
        print(f"✅ PDF успешно сохранен: {output_path}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        # Используем URL по умолчанию
        url = "https://oracc.museum.upenn.edu/saao/saa01/P224487/html"
        output = sys.argv[1] if len(sys.argv) > 1 else "oracc_page.pdf"
    else:
        url = sys.argv[1]
        output = sys.argv[2] if len(sys.argv) > 2 else "page.pdf"

    print_to_pdf(url, output)

