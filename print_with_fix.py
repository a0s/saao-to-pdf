#!/usr/bin/env python3
"""
Скрипт для печати страницы Oracc в PDF с исправлением обрезания текста
"""

import sys

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


def inject_print_styles(page):
    """Инжектирует стили для печати в страницу"""
    page.add_style_tag(content=PRINT_FIX_CSS)

    # Подготовка страницы для печати через JavaScript
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
    page.evaluate(prepare_script)
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
            margin={"top": "1cm", "right": "0.8cm", "bottom": "1.5cm", "left": "0.8cm"},
            print_background=False,
            prefer_css_page_size=True,
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
