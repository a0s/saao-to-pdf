#!/usr/bin/env python3
"""
Fix Section Hrefs from data-zoom
Исправление section_href для всех секций, извлекая data-zoom из первого item
"""

import json
import logging
import os

from playwright.sync_api import sync_playwright

# Настройка логирования
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Константы
METADATA_FILE = "links_metadata.json"
BASE_URL = "https://oracc.museum.upenn.edu/saao"
TIMEOUT = 30000  # 30 секунд


def load_metadata():
    """Загрузить существующие метаданные"""
    if os.path.exists(METADATA_FILE):
        try:
            with open(METADATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Ошибка при загрузке {METADATA_FILE}: {e}")
            return {"sections": []}
    return {"sections": []}


def save_metadata(metadata):
    """Сохранить метаданные"""
    try:
        with open(METADATA_FILE, "w", encoding="utf-8") as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)
        logger.info(f"Метаданные сохранены в {METADATA_FILE}")
    except Exception as e:
        logger.error(f"Ошибка при сохранении {METADATA_FILE}: {e}")


def get_zoom_from_item(page, item_url):
    """Получить значение data-zoom из элемента p4Pager на странице item"""
    try:
        # Открываем страницу item
        logger.info(f"Открытие страницы item: {item_url}")
        page.goto(item_url, wait_until="domcontentloaded", timeout=TIMEOUT)
        page.wait_for_timeout(2000)  # Пауза для полной загрузки

        # Находим элемент p4Pager
        p4pager = page.locator("div#p4Pager")
        p4pager.wait_for(state="visible", timeout=TIMEOUT)

        # Получаем значение data-zoom
        data_zoom = p4pager.get_attribute("data-zoom", timeout=2000)

        if data_zoom:
            logger.info(f"Найдено data-zoom: {data_zoom}")
            return data_zoom
        else:
            logger.warning("Не удалось найти атрибут data-zoom в элементе p4Pager")
            return None

    except Exception as e:
        logger.error(f"Ошибка при получении data-zoom из item {item_url}: {e}")
        import traceback

        logger.debug(traceback.format_exc())
        return None


def fix_section_hrefs_from_data_zoom(metadata):
    """Исправить section_href для всех секций, извлекая data-zoom из первого item"""
    fixed_count = 0
    skipped_count = 0
    error_count = 0

    with sync_playwright() as p:
        # Запускаем браузер
        logger.info("Запуск браузера...")
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(viewport={"width": 1920, "height": 10000})
        page = context.new_page()

        try:
            sections = metadata.get("sections", [])
            total_sections = len(sections)

            for idx, section in enumerate(sections, 1):
                section_name = section.get("section_name", "")
                section_href = section.get("section_href", "")

                logger.info(f"\n{'='*60}")
                logger.info(
                    f"[{idx}/{total_sections}] Обработка раздела: {section_name}"
                )
                logger.info(f"Текущий section_href: {section_href}")
                logger.info(f"{'='*60}")

                # Получаем первый item из секции
                items = section.get("items", [])
                if not items:
                    logger.warning(
                        f"Раздел '{section_name}' не содержит items, пропускаем"
                    )
                    skipped_count += 1
                    continue

                first_item = items[0]
                item_href = first_item.get("item_href", "")

                if not item_href:
                    logger.warning(
                        f"Первый item раздела '{section_name}' не имеет href, пропускаем"
                    )
                    skipped_count += 1
                    continue

                # Получаем data-zoom из первого item
                data_zoom = get_zoom_from_item(page, item_href)

                if data_zoom:
                    # Формируем section_href с data-zoom
                    section_url = f"{BASE_URL}?zoom={data_zoom}"
                    section["section_href"] = section_url
                    fixed_count += 1
                    logger.info(
                        f"✓ Исправлен section_href для '{section_name}': {section_url}"
                    )

                    # Сохраняем метаданные после каждого исправления
                    save_metadata(metadata)
                else:
                    error_count += 1
                    logger.error(
                        f"✗ Не удалось получить data-zoom для раздела '{section_name}'"
                    )

        except Exception as e:
            logger.error(f"Критическая ошибка: {e}")
        finally:
            # Закрываем браузер
            logger.info("Закрытие браузера...")
            browser.close()

    logger.info("\n" + "=" * 60)
    logger.info("Исправление section_href завершено!")
    logger.info(f"Исправлено: {fixed_count}")
    logger.info(f"Пропущено: {skipped_count}")
    logger.info(f"Ошибок: {error_count}")
    logger.info("=" * 60)


def main():
    """Основная функция"""
    logger.info("Загрузка метаданных...")
    metadata = load_metadata()

    sections_count = len(metadata.get("sections", []))
    logger.info(f"Загружено разделов: {sections_count}")

    if sections_count == 0:
        logger.error("Нет разделов для обработки")
        return

    # Исправляем section_href
    fix_section_hrefs_from_data_zoom(metadata)

    logger.info("Готово!")


if __name__ == "__main__":
    main()
