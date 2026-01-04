#!/usr/bin/env python3
"""
SAA Screenshot Creator
Создание скриншотов на основе собранных метаданных
"""

import json
import logging
import os
import re
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

# Настройка логирования
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Константы
METADATA_FILE = "links_metadata.json"
DATA_DIR = "data"
TIMEOUT = 30000  # 30 секунд


def sanitize_filename(filename):
    """Очистка имени файла от недопустимых символов"""
    # Удаляем недопустимые символы для файловой системы
    filename = re.sub(r'[<>:"/\\|?*]', "", filename)
    # Заменяем множественные пробелы на один
    filename = re.sub(r"\s+", " ", filename)
    # Убираем пробелы в начале и конце
    filename = filename.strip()
    return filename


def load_metadata():
    """Загрузить метаданные"""
    if not os.path.exists(METADATA_FILE):
        logger.error(f"Файл {METADATA_FILE} не найден! Сначала запустите collect_links.py")
        return None

    try:
        with open(METADATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Ошибка при загрузке {METADATA_FILE}: {e}")
        return None


def save_metadata(metadata):
    """Сохранить метаданные"""
    try:
        with open(METADATA_FILE, "w", encoding="utf-8") as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Ошибка при сохранении {METADATA_FILE}: {e}")


def create_screenshot(page, item, section_name):
    """Создать скриншот для одного элемента"""
    item_name = item["item_name"]
    item_href = item["item_href"]

    # Проверяем, не обработан ли уже
    if item.get("status") == "completed" and item.get("screenshot_path"):
        screenshot_path = Path(item["screenshot_path"])
        if screenshot_path.exists():
            logger.info(f"Пропускаем уже обработанный: {section_name} / {item_name}")
            return True

    try:
        logger.info(f"Обработка: {section_name} / {item_name}")

        # Переходим по ссылке
        if item_href.startswith("http"):
            page.goto(item_href, wait_until="networkidle", timeout=30000)
        else:
            # Относительный URL - строим полный путь
            base_url = page.url.split("?")[0].rsplit("/", 1)[0]
            full_url = f"{base_url}/{item_href.lstrip('/')}"
            page.goto(full_url, wait_until="networkidle", timeout=30000)

        page.wait_for_timeout(2000)  # Дополнительная пауза

        # Ждем загрузки контента
        text_div = page.locator("div#p4XtfData > div.text")
        text_div.wait_for(state="visible", timeout=TIMEOUT)

        # Дополнительная пауза для полной загрузки
        page.wait_for_timeout(2000)

        # Создаем директорию
        safe_section_name = sanitize_filename(section_name)
        safe_item_name = sanitize_filename(item_name)
        dir_path = Path(DATA_DIR) / safe_section_name
        dir_path.mkdir(parents=True, exist_ok=True)

        # Путь для сохранения скриншота
        screenshot_path = dir_path / f"{safe_item_name}.png"
        screenshot_path_str = str(screenshot_path)

        # Делаем полный скриншот элемента
        # Получаем полную высоту и ширину элемента через JavaScript
        element_handle = text_div.element_handle()
        element_height = page.evaluate("(el) => el.scrollHeight", element_handle)
        element_width = page.evaluate("(el) => el.scrollWidth", element_handle)

        # Получаем текущий viewport
        original_viewport = page.viewport_size

        try:
            # Устанавливаем максимальный размер viewport для захвата всего элемента
            # Добавляем запас для заголовков и отступов
            max_width = max(int(element_width) + 100, 1920)
            max_height = max(
                int(element_height) + 500, 10000
            )  # Минимум 10000px для длинных элементов

            # Устанавливаем большой viewport
            page.set_viewport_size({"width": max_width, "height": max_height})
            page.wait_for_timeout(1000)  # Даем время на изменение размера

            # Прокручиваем к началу элемента
            text_div.scroll_into_view_if_needed(timeout=TIMEOUT)
            page.wait_for_timeout(500)

            # Получаем позицию элемента после изменения viewport
            box = text_div.bounding_box(timeout=TIMEOUT)

            if box:
                # Делаем скриншот всей страницы с обрезкой по элементу
                # Используем реальную высоту элемента для clip
                clip_height = min(
                    int(element_height), max_height - int(box["y"]) - 100
                )
                page.screenshot(
                    path=screenshot_path_str,
                    clip={
                        "x": max(0, int(box["x"])),
                        "y": max(0, int(box["y"])),
                        "width": min(int(box["width"]), max_width - int(box["x"])),
                        "height": clip_height,
                    },
                    timeout=TIMEOUT,
                )
            else:
                # Если не удалось получить bounding box, делаем скриншот элемента напрямую
                # Но сначала убедимся, что viewport достаточно большой
                text_div.screenshot(path=screenshot_path_str, timeout=TIMEOUT)
        finally:
            # Восстанавливаем оригинальный viewport
            if original_viewport:
                page.set_viewport_size(original_viewport)
                page.wait_for_timeout(500)

        logger.info(f"Скриншот сохранен: {screenshot_path_str}")

        # Обновляем метаданные
        item["screenshot_path"] = screenshot_path_str
        item["status"] = "completed"

        return True

    except PlaywrightTimeoutError as e:
        logger.error(f"Таймаут при обработке {section_name} / {item_name}: {e}")
        item["status"] = "failed"
        item["error"] = str(e)
        return False
    except Exception as e:
        logger.error(f"Ошибка при обработке {section_name} / {item_name}: {e}")
        item["status"] = "failed"
        item["error"] = str(e)
        return False


def main():
    """Основная функция"""
    metadata = load_metadata()
    if not metadata:
        return

    sections = metadata.get("sections", [])
    logger.info(f"Загружено разделов: {len(sections)}")

    # Подсчитываем общее количество элементов
    total_items = sum(len(section.get("items", [])) for section in sections)
    completed_items = sum(
        1
        for section in sections
        for item in section.get("items", [])
        if item.get("status") == "completed"
    )
    logger.info(f"Всего элементов: {total_items}, уже обработано: {completed_items}")

    with sync_playwright() as p:
        # Запускаем браузер (headless=False для визуального контроля)
        logger.info("Запуск браузера...")
        browser = p.chromium.launch(headless=False)
        # Создаем контекст с максимальным размером viewport для захвата длинных элементов
        context = browser.new_context(viewport={"width": 1920, "height": 10000})
        page = context.new_page()

        try:
            # Открываем базовую страницу для навигации
            logger.info("Открытие базовой страницы...")
            page.goto("https://oracc.museum.upenn.edu/saao?zoom=1", wait_until="networkidle", timeout=60000)
            page.wait_for_timeout(2000)

            # Обрабатываем каждый раздел
            for section_idx, section in enumerate(sections, 1):
                section_name = section["section_name"]
                items = section.get("items", [])

                logger.info(f"\n{'='*60}")
                logger.info(
                    f"Обработка раздела {section_idx}/{len(sections)}: {section_name}"
                )
                logger.info(f"Элементов в разделе: {len(items)}")
                logger.info(f"{'='*60}")

                # Обрабатываем каждый элемент
                for item_idx, item in enumerate(items, 1):
                    logger.info(
                        f"Элемент {item_idx}/{len(items)} в разделе '{section_name}'"
                    )

                    create_screenshot(page, item, section_name)

                    # Сохраняем метаданные после каждого элемента
                    save_metadata(metadata)

            logger.info("\n" + "=" * 60)
            logger.info("Создание скриншотов завершено!")

            # Финальная статистика
            completed = sum(
                1
                for section in sections
                for item in section.get("items", [])
                if item.get("status") == "completed"
            )
            failed = sum(
                1
                for section in sections
                for item in section.get("items", [])
                if item.get("status") == "failed"
            )
            pending = sum(
                1
                for section in sections
                for item in section.get("items", [])
                if item.get("status") == "pending"
            )

            logger.info(f"Обработано успешно: {completed}")
            logger.info(f"Ошибок: {failed}")
            logger.info(f"Ожидают обработки: {pending}")
            logger.info("=" * 60)

        except Exception as e:
            logger.error(f"Критическая ошибка: {e}")
        finally:
            # Закрываем браузер
            logger.info("Закрытие браузера...")
            browser.close()


if __name__ == "__main__":
    main()

