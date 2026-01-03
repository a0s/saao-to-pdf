// Скрипт для инжекта стилей печати на страницу Oracc

(function() {
  // CSS стили для исправления обрезания текста при печати
  const printStyles = `
    @media print {
      @page {
        margin: 1.5cm 1cm 2cm 1cm !important;
        size: A4;
      }

      body {
        margin: 0 !important;
        padding: 0 !important;
        overflow: visible !important;
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

      h1, h2, h3, h4, h5, h6 {
        page-break-after: avoid !important;
        page-break-inside: avoid !important;
        page-break-before: avoid !important;
        orphans: 4 !important;
        widows: 4 !important;
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

      p, div, section, article {
        orphans: 4 !important;
        widows: 4 !important;
        page-break-inside: avoid !important;
        word-break: break-word !important;
        overflow-wrap: break-word !important;
      }

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

      nav, header, footer, .navigation, .menu, .sidebar {
        display: none !important;
      }

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
  `;

  // Создаем элемент style и добавляем стили
  const styleElement = document.createElement('style');
  styleElement.type = 'text/css';
  styleElement.id = 'print-fix-styles';
  styleElement.textContent = printStyles;

  // Добавляем стили в head документа
  if (document.head) {
    document.head.appendChild(styleElement);
    console.log('✅ Стили для печати успешно добавлены!');
  } else {
    // Если head еще не загружен, ждем
    document.addEventListener('DOMContentLoaded', function() {
      document.head.appendChild(styleElement);
      console.log('✅ Стили для печати успешно добавлены!');
    });
  }
})();

