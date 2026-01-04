#!/usr/bin/env python3
"""Проверка структуры PDF файла"""

from pypdf import PdfReader
import sys

def check_pdf(pdf_path):
    """Проверяет структуру PDF"""
    try:
        reader = PdfReader(pdf_path)
        num_pages = len(reader.pages)

        print(f"📄 PDF файл: {pdf_path}")
        print(f"📊 Количество страниц: {num_pages}")
        print(f"📏 Метаданные: {reader.metadata if reader.metadata else 'Нет метаданных'}")
        print("\n" + "="*60)
        print("Проверка страниц:")
        print("="*60)

        for i, page in enumerate(reader.pages, 1):
            text = page.extract_text()
            lines = text.split('\n')
            non_empty_lines = [l for l in lines if l.strip()]

            print(f"\nСтраница {i}:")
            print(f"  - Строк текста: {len(non_empty_lines)}")
            print(f"  - Первые 3 строки:")
            for line in non_empty_lines[:3]:
                preview = line[:80] + "..." if len(line) > 80 else line
                print(f"    • {preview}")

            if i == 1:
                # Проверяем наличие таблиц (ищем характерные паттерны)
                if 'table' in text.lower() or '|' in text or '\t' in text:
                    print(f"  ⚠️  Возможные таблицы обнаружены на странице {i}")

        print("\n" + "="*60)
        print("✅ Проверка завершена")

    except Exception as e:
        print(f"❌ Ошибка при проверке PDF: {e}")
        return False

    return True

if __name__ == "__main__":
    pdf_path = sys.argv[1] if len(sys.argv) > 1 else "oracc_page.pdf"
    check_pdf(pdf_path)

