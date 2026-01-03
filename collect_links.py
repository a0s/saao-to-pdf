#!/usr/bin/env python3
"""
SAA Links Collector
Сбор всех ссылок из разделов SAA и сохранение метаданных в JSON
"""

import json
import logging
import os
import re

from playwright.sync_api import sync_playwright

# Настройка логирования
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Константы
BASE_URL = "https://oracc.museum.upenn.edu/saao"
METADATA_FILE = "links_metadata.json"
TIMEOUT = 30000  # 30 секунд


def get_links_from_current_page(page):
    """Получить все ссылки с текущей страницы таблицы"""
    links = []
    try:
        # Ждем появления таблицы
        table_locator = page.locator("table.xmd")
        table_locator.wait_for(state="visible", timeout=TIMEOUT)

        # Собираем ссылки с текущей страницы
        link_elements = table_locator.locator("a").all()
        for link in link_elements:
            try:
                text = link.inner_text(timeout=5000).strip()
                href = link.get_attribute("href", timeout=5000)
                if text:
                    links.append({"text": text, "href": href})
            except Exception as e:
                logger.debug(f"Ошибка при извлечении ссылки: {e}")
                continue
    except Exception as e:
        logger.error(f"Ошибка при получении ссылок с текущей страницы: {e}")

    return links


def get_total_pages(page):
    """Получить общее количество страниц"""
    try:
        page_nav = page.locator("div#p4PageNav")
        if page_nav.is_visible(timeout=2000):
            page_info_text = page.locator("p.p3toccenter.bg-dk").inner_text(
                timeout=5000
            )
            logger.info(f"Информация о страницах: {page_info_text}")

            match = re.search(r"(\d+)\s+pages?", page_info_text)
            if match:
                return int(match.group(1))
    except Exception as e:
        logger.debug(f"Ошибка при определении количества страниц: {e}")

    return 1


def go_to_next_page(page):
    """Перейти на следующую страницу таблицы"""
    try:
        next_button = page.locator("img#p4PageNext")
        if next_button.is_visible(timeout=1000):
            logger.info("Переход на следующую страницу...")
            next_button.click(timeout=3000)
            page.wait_for_timeout(500)  # Минимальная пауза для загрузки

            # Ждем появления таблицы на новой странице
            table_locator = page.locator("table.xmd")
            table_locator.wait_for(state="visible", timeout=10000)
            return True
    except Exception as e:
        logger.warning(f"Ошибка при переходе на следующую страницу: {e}")

    return False


def return_to_table_from_item(page, section_href):
    """Вернуться к таблице после просмотра элемента"""
    try:
        # Используем browser back для возврата
        page.go_back(wait_until="domcontentloaded", timeout=15000)
        page.wait_for_timeout(300)  # Минимальная пауза

        # Ждем появления таблицы
        table_locator = page.locator("table.xmd")
        table_locator.wait_for(state="visible", timeout=10000)
        return True
    except Exception as e:
        logger.warning(f"Ошибка при возврате к таблице: {e}")
        # Если не получилось через back, пытаемся перейти по ссылке раздела
        try:
            if section_href.startswith("http"):
                page.goto(section_href, wait_until="domcontentloaded", timeout=15000)
            else:
                base_url = page.url.split("?")[0].rsplit("/", 1)[0]
                full_url = f"{base_url}/{section_href.lstrip('/')}"
                page.goto(full_url, wait_until="domcontentloaded", timeout=15000)
            page.wait_for_timeout(300)
            table_locator = page.locator("table.xmd")
            table_locator.wait_for(state="visible", timeout=10000)
            return True
        except Exception as e2:
            logger.error(f"Не удалось вернуться к таблице: {e2}")
            return False


def get_zoom_from_item(page, item_url):
    """Получить значение data-zoom из элемента p4Pager на странице item"""
    try:
        # Открываем страницу item
        logger.info(f"Открытие страницы item для получения data-zoom: {item_url}")
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


def collect_all_items_from_section(page, section_name, section_href, metadata):
    """Собрать все элементы из раздела с обработкой пагинации"""
    items = []

    try:
        # Получаем общее количество страниц
        total_pages = get_total_pages(page)
        logger.info(f"Всего страниц в таблице: {total_pages}")

        # Обрабатываем каждую страницу по очереди
        for current_page in range(1, total_pages + 1):
            logger.info(f"Сбор ссылок со страницы {current_page} из {total_pages}")

            # Получаем ссылки с текущей страницы (получаем элементы, а не только текст)
            table_locator = page.locator("table.xmd")
            table_locator.wait_for(state="visible", timeout=TIMEOUT)
            link_elements = table_locator.locator("a").all()

            logger.info(
                f"Найдено ссылок на странице {current_page}: {len(link_elements)}"
            )

            # Собираем информацию о ссылках, обрабатывая только первую ссылку в каждой строке
            # (чтобы избежать дублирования - в строке есть ссылка на номер SAA и на название)
            link_data = []
            processed_rows = set()

            for link_element in link_elements:
                try:
                    # Получаем ID строки (родительский tr)
                    try:
                        row = link_element.locator("xpath=ancestor::tr").first
                        row_text = row.inner_text(timeout=1000).strip()
                        # Используем первые 50 символов строки как уникальный идентификатор
                        row_id = row_text[:50] if row_text else ""
                    except Exception:
                        row_text = ""
                        row_id = ""

                    # Пропускаем, если эту строку уже обработали
                    if row_id and row_id in processed_rows:
                        continue

                    # Получаем текст самой ссылки
                    link_text = link_element.inner_text(timeout=1000).strip()

                    # Если не удалось получить row_text, используем link_text
                    if not row_text:
                        row_text = link_text

                    link_data.append(
                        {
                            "link_text": link_text,
                            "row_text": row_text,
                            "element": link_element,
                            "row_id": row_id,
                        }
                    )

                    if row_id:
                        processed_rows.add(row_id)
                except Exception:
                    continue

            # Теперь проходим по ссылкам и кликаем, записывая URL
            for link_idx, link_info in enumerate(link_data):
                try:
                    link_text = link_info["link_text"]
                    row_text = link_info["row_text"]

                    # Парсим название элемента
                    # Пробуем разные варианты разделителей
                    item_name = ""
                    item_text = ""

                    # Вариант 1: Табуляция в тексте ссылки
                    if "\t" in link_text:
                        parts = link_text.split("\t", 1)
                        item_name = parts[0].strip()
                        item_text = parts[1].strip()
                    # Вариант 2: Табуляция в тексте строки
                    elif "\t" in row_text:
                        parts = row_text.split("\t", 1)
                        item_name = parts[0].strip()
                        item_text = parts[1].strip()
                    # Вариант 3: Формат "SAA XX XXX название" - номер в начале
                    elif re.match(r"^SAA\s+\d+\s+\d+", link_text):
                        # Это номер, ищем название в строке
                        parts = row_text.split(link_text, 1)
                        item_name = link_text
                        item_text = parts[1].strip() if len(parts) > 1 else ""
                    # Вариант 4: Только название (без номера SAA)
                    else:
                        # Это может быть только название
                        item_name = link_text
                        item_text = ""

                    # Если item_name пустой, используем link_text
                    if not item_name:
                        item_name = link_text

                    logger.info(
                        f"  Обработка ссылки {link_idx + 1}/{len(link_data)}: {item_name}"
                    )

                    # Используем сохраненный элемент ссылки
                    link_element = link_info["element"]

                    # Проверяем, что элемент еще валиден (может стать невалидным после возврата)
                    try:
                        # Проверяем, что элемент все еще в DOM
                        link_element.is_visible(timeout=1000)
                    except Exception:
                        # Если элемент невалиден, находим его заново
                        table_locator = page.locator("table.xmd")
                        table_locator.wait_for(state="visible", timeout=TIMEOUT)
                        all_links = table_locator.locator("a").all()

                        found_link = None
                        for link in all_links:
                            try:
                                if link.inner_text(timeout=2000).strip() == link_text:
                                    found_link = link
                                    break
                            except Exception:
                                continue

                        if not found_link:
                            logger.warning(
                                f"Не удалось найти ссылку с текстом: {item_name}"
                            )
                            items.append(
                                {
                                    "item_name": item_name,
                                    "item_full_name": (
                                        row_text if row_text else link_text
                                    ),
                                    "item_text": item_text,
                                    "item_href": "",
                                    "status": "pending",
                                    "error": "Link not found",
                                }
                            )
                            continue
                        link_element = found_link

                    # Кликаем по ссылке и записываем URL после перехода
                    try:
                        link_element.click(timeout=TIMEOUT)
                        page.wait_for_timeout(500)  # Минимальная пауза для перехода

                        # Получаем URL после перехода
                        item_url = page.url

                        # Возвращаемся назад к таблице
                        if not return_to_table_from_item(page, section_href):
                            logger.error(
                                f"Не удалось вернуться к таблице после {item_name}"
                            )
                            # Пытаемся перезагрузить страницу раздела
                            if section_href.startswith("http"):
                                page.goto(
                                    section_href,
                                    wait_until="networkidle",
                                    timeout=30000,
                                )
                            else:
                                base_url = item_url.split("?")[0].rsplit("/", 1)[0]
                                full_url = f"{base_url}/{section_href.lstrip('/')}"
                                page.goto(
                                    full_url, wait_until="networkidle", timeout=30000
                                )
                            page.wait_for_timeout(2000)

                            # Если нужно, переходим на нужную страницу пагинации
                            if current_page > 1:
                                for _ in range(current_page - 1):
                                    go_to_next_page(page)

                        new_item = {
                            "item_name": item_name,
                            "item_full_name": row_text if row_text else link_text,
                            "item_text": item_text,
                            "item_href": item_url,
                            "status": "pending",
                        }
                        items.append(new_item)

                        # Сохраняем метаданные после каждого элемента
                        # Находим текущий раздел в metadata и обновляем его
                        section_found = False
                        for section in metadata.get("sections", []):
                            if section.get("section_name") == section_name:
                                section["items"] = items
                                section_found = True
                                break

                        # Если раздела еще нет, создаем его
                        if not section_found:
                            metadata.setdefault("sections", []).append(
                                {
                                    "section_name": section_name,
                                    "section_href": section_href,
                                    "items": items,
                                }
                            )

                        save_metadata(metadata)

                    except Exception as e:
                        logger.error(f"Ошибка при обработке ссылки {item_name}: {e}")
                        # Добавляем с пустым href, чтобы не потерять данные
                        items.append(
                            {
                                "item_name": item_name,
                                "item_full_name": row_text if row_text else link_text,
                                "item_text": item_text,
                                "item_href": "",
                                "status": "pending",
                                "error": str(e),
                            }
                        )
                        # Пытаемся вернуться к таблице
                        return_to_table_from_item(page, section_href)

                except Exception as e:
                    logger.error(f"Ошибка при обработке ссылки: {e}")
                    continue

            # Переходим на следующую страницу, если есть
            if current_page < total_pages:
                if not go_to_next_page(page):
                    logger.warning(f"Не удалось перейти на страницу {current_page + 1}")
                    break

    except Exception as e:
        logger.error(f"Ошибка при сборе элементов из раздела {section_name}: {e}")

    return items


def load_metadata():
    """Загрузить существующие метаданные"""
    if os.path.exists(METADATA_FILE):
        try:
            with open(METADATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Ошибка при загрузке {METADATA_FILE}: {e}")
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


def section_exists(metadata, section_name):
    """Проверить, существует ли раздел в метаданных"""
    for section in metadata.get("sections", []):
        if section.get("section_name") == section_name:
            return True
    return False


def main():
    """Основная функция"""
    metadata = load_metadata()
    logger.info(f"Загружено разделов: {len(metadata.get('sections', []))}")

    with sync_playwright() as p:
        # Запускаем браузер
        logger.info("Запуск браузера...")
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(viewport={"width": 1920, "height": 10000})
        page = context.new_page()

        try:
            # Открываем страницу
            initial_url = f"{BASE_URL}?zoom=1"
            logger.info(f"Открытие страницы: {initial_url}")
            page.goto(initial_url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(1000)  # Минимальная пауза для загрузки

            # Находим все ссылки в левой колонке
            logger.info("Поиск ссылок в левой колонке...")
            menu_outline = page.locator("div#p4MenuOutline")
            menu_outline.wait_for(state="visible", timeout=TIMEOUT)

            # Находим все ссылки в меню
            menu_links = menu_outline.locator("a").all()
            logger.info(f"Найдено ссылок в меню: {len(menu_links)}")

            column_a_links = []
            for link in menu_links:
                try:
                    text = link.inner_text(timeout=5000).strip()
                    href = link.get_attribute("href", timeout=5000)
                    if text and href:
                        column_a_links.append(
                            {"text": text, "href": href, "element": link}
                        )
                        logger.info(f"  - {text}")
                except Exception as e:
                    logger.warning(f"Ошибка при извлечении ссылки меню: {e}")
                    continue

            # Обрабатываем каждую ссылку из колонки A
            for column_a_link in column_a_links:
                section_name = column_a_link["text"]
                section_href = column_a_link["href"]

                # Пропускаем, если раздел уже собран
                if section_exists(metadata, section_name):
                    logger.info(f"Раздел '{section_name}' уже собран, пропускаем")
                    continue

                logger.info(f"\n{'='*60}")
                logger.info(f"Обработка раздела: {section_name}")
                logger.info(f"{'='*60}")

                try:
                    # Кликаем по ссылке в меню
                    column_a_link["element"].click(timeout=TIMEOUT)
                    page.wait_for_timeout(1000)  # Минимальная пауза для загрузки

                    # Собираем все элементы из раздела
                    items = collect_all_items_from_section(
                        page, section_name, section_href, metadata
                    )

                    # Обновляем section_href, извлекая data-zoom из первого item
                    if items:
                        first_item = items[0]
                        item_href = first_item.get("item_href", "")
                        if item_href:
                            logger.info(
                                f"Получение data-zoom для обновления section_href из первого item..."
                            )
                            data_zoom = get_zoom_from_item(page, item_href)
                            if data_zoom:
                                section_href = f"{BASE_URL}?zoom={data_zoom}"
                                logger.info(
                                    f"✓ Обновлен section_href для '{section_name}': {section_href}"
                                )
                            else:
                                logger.warning(
                                    f"Не удалось получить data-zoom для '{section_name}', используется исходный section_href"
                                )

                            # Возвращаемся к таблице раздела после получения data-zoom
                            return_to_table_from_item(page, section_href)
                        else:
                            logger.warning(
                                f"Первый item раздела '{section_name}' не имеет href, используется исходный section_href"
                            )
                    else:
                        logger.warning(
                            f"Раздел '{section_name}' не содержит items, используется исходный section_href"
                        )

                    # Добавляем раздел в метаданные
                    section_data = {
                        "section_name": section_name,
                        "section_href": section_href,
                        "items": items,
                    }
                    metadata["sections"].append(section_data)

                    logger.info(
                        f"Собрано элементов из раздела '{section_name}': {len(items)}"
                    )

                    # Сохраняем метаданные после каждого раздела
                    save_metadata(metadata)

                except Exception as e:
                    logger.error(f"Ошибка при обработке раздела {section_name}: {e}")
                    continue

            logger.info("\n" + "=" * 60)
            logger.info("Сбор ссылок завершен!")
            logger.info(f"Всего разделов: {len(metadata.get('sections', []))}")
            total_items = sum(
                len(section.get("items", []))
                for section in metadata.get("sections", [])
            )
            logger.info(f"Всего элементов: {total_items}")
            logger.info("=" * 60)

        except Exception as e:
            logger.error(f"Критическая ошибка: {e}")
        finally:
            # Закрываем браузер
            logger.info("Закрытие браузера...")
            browser.close()


if __name__ == "__main__":
    main()
