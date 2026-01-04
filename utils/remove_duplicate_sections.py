#!/usr/bin/env python3
"""
Remove Duplicate Sections
Находит и удаляет дублированные секции в links_metadata.json
Сравнивает секции по названию (section_name) и ссылкам внутри (item_href)
"""

import json
import logging
import os
from collections import defaultdict

# Настройка логирования
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Константы
METADATA_FILE = "links_metadata.json"
BACKUP_FILE = "links_metadata.json.backup"


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
        # Создаем резервную копию перед сохранением
        if os.path.exists(METADATA_FILE):
            import shutil
            shutil.copy2(METADATA_FILE, BACKUP_FILE)
            logger.info(f"Создана резервная копия: {BACKUP_FILE}")

        with open(METADATA_FILE, "w", encoding="utf-8") as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)
        logger.info(f"Метаданные сохранены в {METADATA_FILE}")
    except Exception as e:
        logger.error(f"Ошибка при сохранении {METADATA_FILE}: {e}")


def get_section_links(section):
    """Получить набор ссылок из секции"""
    links = set()
    for item in section.get("items", []):
        href = item.get("item_href", "")
        if href:
            links.add(href)
    return links


def sections_are_duplicates(section1, section2):
    """
    Проверить, являются ли две секции дубликатами
    Сравнивает по названию и набору ссылок
    """
    # Сравниваем названия
    if section1.get("section_name") != section2.get("section_name"):
        return False

    # Сравниваем наборы ссылок
    links1 = get_section_links(section1)
    links2 = get_section_links(section2)

    # Если наборы ссылок идентичны, это дубликат
    if links1 == links2:
        return True

    # Также проверяем, если одна секция содержит все ссылки другой
    # (возможно, одна секция - подмножество другой)
    if links1 and links2:
        if links1.issubset(links2) or links2.issubset(links1):
            logger.warning(
                f"Секция '{section1.get('section_name')}' имеет частичное совпадение ссылок: "
                f"{len(links1)} vs {len(links2)}"
            )
            # Если одна секция содержит все ссылки другой, считаем их дубликатами
            # и оставляем ту, где больше ссылок
            return True

    return False


def remove_duplicate_sections(metadata):
    """Найти и удалить дублированные секции"""
    sections = metadata.get("sections", [])
    if not sections:
        logger.warning("Нет секций для обработки")
        return metadata, 0

    logger.info(f"Всего секций для проверки: {len(sections)}")

    # Группируем секции по названию для быстрого поиска
    sections_by_name = defaultdict(list)
    for idx, section in enumerate(sections):
        name = section.get("section_name", "")
        sections_by_name[name].append((idx, section))

    # Находим дубликаты
    indices_to_remove = set()
    duplicates_found = []

    for section_name, section_list in sections_by_name.items():
        if len(section_list) > 1:
            logger.info(
                f"Найдено {len(section_list)} секций с названием '{section_name}'"
            )

            # Сравниваем каждую пару секций
            for i in range(len(section_list)):
                idx1, section1 = section_list[i]
                if idx1 in indices_to_remove:
                    continue

                for j in range(i + 1, len(section_list)):
                    idx2, section2 = section_list[j]
                    if idx2 in indices_to_remove:
                        continue

                    if sections_are_duplicates(section1, section2):
                        # Оставляем первую секцию, удаляем остальные
                        links1 = get_section_links(section1)
                        links2 = get_section_links(section2)

                        # Если вторая секция содержит больше ссылок, оставляем её
                        if len(links2) > len(links1):
                            indices_to_remove.add(idx1)
                            duplicates_found.append(
                                {
                                    "name": section_name,
                                    "removed_index": idx1,
                                    "kept_index": idx2,
                                    "links_count": len(links1),
                                }
                            )
                            logger.info(
                                f"  Дубликат найден: удаляем секцию #{idx1} (оставляем #{idx2} с {len(links2)} ссылками)"
                            )
                            break  # Уже удалили section1, переходим к следующей
                        else:
                            indices_to_remove.add(idx2)
                            duplicates_found.append(
                                {
                                    "name": section_name,
                                    "removed_index": idx2,
                                    "kept_index": idx1,
                                    "links_count": len(links2),
                                }
                            )
                            logger.info(
                                f"  Дубликат найден: удаляем секцию #{idx2} (оставляем #{idx1} с {len(links1)} ссылками)"
                            )

    # Удаляем дубликаты (в обратном порядке, чтобы индексы не сдвигались)
    if indices_to_remove:
        logger.info(f"\nВсего найдено дубликатов для удаления: {len(indices_to_remove)}")
        for idx in sorted(indices_to_remove, reverse=True):
            removed_section = sections.pop(idx)
            logger.debug(
                f"Удалена секция #{idx}: '{removed_section.get('section_name')}'"
            )

        metadata["sections"] = sections
        logger.info(f"Осталось секций: {len(sections)}")
    else:
        logger.info("Дубликаты не найдены")

    return metadata, len(indices_to_remove)


def main():
    """Основная функция"""
    logger.info("=" * 60)
    logger.info("Поиск и удаление дублированных секций")
    logger.info("=" * 60)

    # Загружаем метаданные
    metadata = load_metadata()
    if not metadata or "sections" not in metadata:
        logger.error("Не удалось загрузить метаданные или файл пуст")
        return

    initial_count = len(metadata.get("sections", []))

    # Удаляем дубликаты
    metadata, removed_count = remove_duplicate_sections(metadata)

    if removed_count > 0:
        # Сохраняем обновленные метаданные
        save_metadata(metadata)
        logger.info("=" * 60)
        logger.info(
            f"Готово! Удалено {removed_count} дублированных секций. "
            f"Было: {initial_count}, стало: {len(metadata.get('sections', []))}"
        )
        logger.info(f"Резервная копия сохранена в: {BACKUP_FILE}")
    else:
        logger.info("=" * 60)
        logger.info("Дубликаты не найдены, файл не изменен")


if __name__ == "__main__":
    main()

