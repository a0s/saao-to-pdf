#!/usr/bin/env python3
"""
SAA Screenshot Scraper
Автоматический скрапинг страниц SAA с сохранением скриншотов
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
BASE_URL = "https://oracc.museum.upenn.edu/saao?zoom=1"
SCRAPED_PAGES_FILE = "scraped_pages.json"
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


def load_scraped_pages():
    """Загрузка списка уже пройденных страниц"""
    if os.path.exists(SCRAPED_PAGES_FILE):
        try:
            with open(SCRAPED_PAGES_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Ошибка при загрузке {SCRAPED_PAGES_FILE}: {e}")
            return {}
    return {}


def save_scraped_pages(scraped_pages):
    """Сохранение списка пройденных страниц"""
    try:
        with open(SCRAPED_PAGES_FILE, "w", encoding="utf-8") as f:
            json.dump(scraped_pages, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Ошибка при сохранении {SCRAPED_PAGES_FILE}: {e}")


def is_already_scraped(scraped_pages, column_a, column_b):
    """Проверка, была ли страница уже обработана"""
    return column_a in scraped_pages and column_b in scraped_pages[column_a]


def mark_as_scraped(scraped_pages, column_a, column_b):
    """Отметить страницу как обработанную"""
    if column_a not in scraped_pages:
        scraped_pages[column_a] = []
    if column_b not in scraped_pages[column_a]:
        scraped_pages[column_a].append(column_b)


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
                    # Сохраняем текст для поиска элемента позже
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
        if next_button.is_visible(timeout=2000):
            logger.info("Переход на следующую страницу...")
            next_button.click(timeout=5000)
            page.wait_for_timeout(2000)  # Ждем загрузки новой страницы

            # Ждем появления таблицы на новой странице
            table_locator = page.locator("table.xmd")
            table_locator.wait_for(state="visible", timeout=TIMEOUT)
            return True
    except Exception as e:
        logger.warning(f"Ошибка при переходе на следующую страницу: {e}")

    return False


def return_to_table_page(page, column_a_link_element, target_page_num=None):
    """Вернуться к странице с таблицей после просмотра документа"""
    try:
        # Используем клик по элементу ссылки колонки A вместо перехода по URL
        # Это более надежно, так как избегает проблем с javascript: ссылками
        if column_a_link_element:
            # Прокручиваем к элементу меню и кликаем
            column_a_link_element.scroll_into_view_if_needed(timeout=TIMEOUT)
            page.wait_for_timeout(500)
            column_a_link_element.click(timeout=TIMEOUT)
            page.wait_for_timeout(2000)
        else:
            # Если элемент не передан, пытаемся найти ссылку в меню по тексту
            # Но это менее надежно, поэтому лучше передавать элемент
            logger.warning(
                "Элемент ссылки колонки A не передан, пытаемся найти вручную"
            )
            return False

        # Ждем появления таблицы
        table_locator = page.locator("table.xmd")
        table_locator.wait_for(state="visible", timeout=TIMEOUT)

        # Если нужно вернуться на конкретную страницу пагинации
        if target_page_num and target_page_num > 1:
            # Переходим на нужную страницу
            for _ in range(target_page_num - 1):
                if not go_to_next_page(page):
                    break

        return True
    except Exception as e:
        logger.warning(f"Ошибка при возврате к таблице: {e}")
        return False


def scrape_page(page, column_a, column_b_link, scraped_pages):
    """Скрапинг одной страницы и создание скриншота"""
    column_b_text = column_b_link["text"]

    # Проверяем идемпотентность
    if is_already_scraped(scraped_pages, column_a, column_b_text):
        logger.info(
            f"Пропускаем уже обработанную страницу: {column_a} / {column_b_text}"
        )
        return True

    try:
        logger.info(f"Обработка: {column_a} / {column_b_text}")

        # Находим ссылку в таблице по тексту и кликаем по ней
        table_locator = page.locator("table.xmd")
        table_locator.wait_for(state="visible", timeout=TIMEOUT)

        # Получаем все ссылки и ищем нужную по тексту
        all_links = table_locator.locator("a").all()
        found_link = None

        for link in all_links:
            try:
                link_text = link.inner_text(timeout=2000).strip()
                if link_text == column_b_text or column_b_text in link_text:
                    found_link = link
                    break
            except Exception:
                continue

        if not found_link:
            # Если не нашли точное совпадение, пробуем найти по первым словам
            search_words = column_b_text.split()[:3]
            search_text = " ".join(search_words)
            for link in all_links:
                try:
                    link_text = link.inner_text(timeout=2000).strip()
                    if search_text in link_text:
                        found_link = link
                        break
                except Exception:
                    continue

        if not found_link:
            raise Exception(f"Не удалось найти ссылку с текстом: {column_b_text}")

        # Кликаем по найденной ссылке
        found_link.click(timeout=TIMEOUT)

        page.wait_for_timeout(2000)  # Дополнительная пауза

        # Ждем загрузки контента
        text_div = page.locator("div#p4XtfData > div.text")
        text_div.wait_for(state="visible", timeout=TIMEOUT)

        # Дополнительная пауза для полной загрузки
        page.wait_for_timeout(2000)

        # Создаем директорию
        safe_column_a = sanitize_filename(column_a)
        safe_column_b = sanitize_filename(column_b_text)
        dir_path = Path(DATA_DIR) / safe_column_a
        dir_path.mkdir(parents=True, exist_ok=True)

        # Путь для сохранения скриншота
        screenshot_path = dir_path / f"{safe_column_b}.png"

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
                clip_height = min(int(element_height), max_height - int(box["y"]) - 100)
                page.screenshot(
                    path=str(screenshot_path),
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
                text_div.screenshot(path=str(screenshot_path), timeout=TIMEOUT)
        finally:
            # Восстанавливаем оригинальный viewport
            if original_viewport:
                page.set_viewport_size(original_viewport)
                page.wait_for_timeout(500)

        logger.info(f"Скриншот сохранен: {screenshot_path}")

        # Отмечаем как обработанную
        mark_as_scraped(scraped_pages, column_a, column_b_text)
        save_scraped_pages(scraped_pages)

        return True

    except PlaywrightTimeoutError as e:
        logger.error(f"Таймаут при обработке {column_a} / {column_b_text}: {e}")
        return False
    except Exception as e:
        logger.error(f"Ошибка при обработке {column_a} / {column_b_text}: {e}")
        return False


def main():
    """Основная функция"""
    scraped_pages = load_scraped_pages()

    with sync_playwright() as p:
        # Запускаем браузер (headless=False для визуального контроля)
        logger.info("Запуск браузера...")
        browser = p.chromium.launch(headless=False)
        # Создаем контекст с максимальным размером viewport для захвата длинных элементов
        context = browser.new_context(viewport={"width": 1920, "height": 10000})
        page = context.new_page()

        try:
            # Открываем страницу
            logger.info(f"Открытие страницы: {BASE_URL}")
            page.goto(BASE_URL, wait_until="networkidle", timeout=60000)
            page.wait_for_timeout(3000)  # Дополнительная пауза для загрузки

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
                column_a_text = column_a_link["text"]
                column_a_element = column_a_link[
                    "element"
                ]  # Сохраняем элемент для возврата
                logger.info(f"\n{'='*60}")
                logger.info(f"Обработка раздела: {column_a_text}")
                logger.info(f"{'='*60}")

                try:
                    # Кликаем по ссылке в меню
                    column_a_element.click(timeout=TIMEOUT)
                    page.wait_for_timeout(3000)  # Ждем загрузки контента

                    # Получаем общее количество страниц
                    total_pages = get_total_pages(page)
                    logger.info(f"Всего страниц в таблице: {total_pages}")

                    # Обрабатываем каждую страницу по очереди
                    for current_page in range(1, total_pages + 1):
                        logger.info(
                            f"\n--- Страница {current_page} из {total_pages} ---"
                        )

                        # Получаем ссылки с текущей страницы
                        column_b_links = get_links_from_current_page(page)
                        logger.info(
                            f"Найдено ссылок на странице {current_page}: {len(column_b_links)}"
                        )

                        # Обрабатываем каждую ссылку из колонки B на текущей странице
                        for idx, column_b_link in enumerate(column_b_links, 1):
                            logger.info(
                                f"Обработка ссылки {idx}/{len(column_b_links)} на странице {current_page}"
                            )
                            scrape_page(
                                page, column_a_text, column_b_link, scraped_pages
                            )

                            # Возвращаемся назад к таблице (только если это не последняя ссылка на последней странице)
                            if idx < len(column_b_links) or current_page < total_pages:
                                # Находим элемент ссылки колонки A заново (так как после клика DOM может измениться)
                                menu_outline = page.locator("div#p4MenuOutline")
                                menu_outline.wait_for(state="visible", timeout=TIMEOUT)
                                menu_links = menu_outline.locator("a").all()

                                # Ищем нужную ссылку по тексту
                                found_column_a_element = None
                                for link in menu_links:
                                    try:
                                        link_text = link.inner_text(
                                            timeout=2000
                                        ).strip()
                                        if link_text == column_a_text:
                                            found_column_a_element = link
                                            break
                                    except Exception:
                                        continue

                                if found_column_a_element:
                                    return_to_table_page(
                                        page,
                                        found_column_a_element,
                                        target_page_num=current_page,
                                    )
                                else:
                                    logger.warning(
                                        f"Не удалось найти элемент ссылки {column_a_text} для возврата"
                                    )

                        # После обработки всех ссылок на текущей странице, переходим на следующую
                        if current_page < total_pages:
                            if not go_to_next_page(page):
                                logger.warning(
                                    f"Не удалось перейти на страницу {current_page + 1}"
                                )
                                break

                except Exception as e:
                    logger.error(f"Ошибка при обработке раздела {column_a_text}: {e}")
                    continue

            logger.info("\n" + "=" * 60)
            logger.info("Скрапинг завершен!")
            logger.info("=" * 60)

        except Exception as e:
            logger.error(f"Критическая ошибка: {e}")
        finally:
            # Закрываем браузер
            logger.info("Закрытие браузера...")
            browser.close()


if __name__ == "__main__":
    main()
