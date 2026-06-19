#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
EY Data Scraping Automation
ETL-пайплайн для веб-скрейпинга каталога книг.
Стек: requests, BeautifulSoup4, pandas.
"""

import os
import re
import sys
import logging
from datetime import datetime
from typing import List, Dict, Optional

import requests
import pandas as pd
from bs4 import BeautifulSoup

# =============================================================================
# КОНФИГУРАЦИЯ
# =============================================================================
BASE_URL = "http://books.toscrape.com/"
OUTPUT_DIR = "output"
OUTPUT_CSV = os.path.join(OUTPUT_DIR, "data.csv")
OUTPUT_XLSX = os.path.join(OUTPUT_DIR, "scraped_data.xlsx")

RATING_MAP = {
    "One": 1, "Two": 2, "Three": 3, "Four": 4, "Five": 5
}

# =============================================================================
# ЛОГИРОВАНИЕ
# =============================================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


# =============================================================================
# EXTRACT
# =============================================================================
def fetch_html(url: str, timeout: int = 30) -> str:
    """
    Извлекает HTML-контент по указанному URL.
    Обрабатывает сетевые ошибки и HTTP-статусы.
    """
    try:
        logger.info(f"[EXTRACT] Запрос: {url}")
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
            )
        }
        response = requests.get(url, headers=headers, timeout=timeout)
        response.raise_for_status()
        logger.info(f"[EXTRACT] Ответ получен: HTTP {response.status_code}")
        return response.text

    except requests.exceptions.HTTPError as e:
        logger.error(f"[EXTRACT] HTTP ошибка: {e}")
        raise
    except requests.exceptions.ConnectionError as e:
        logger.error(f"[EXTRACT] Ошибка подключения: {e}")
        raise
    except requests.exceptions.Timeout as e:
        logger.error(f"[EXTRACT] Превышен таймаут: {e}")
        raise
    except requests.exceptions.RequestException as e:
        logger.error(f"[EXTRACT] Критическая сетевая ошибка: {e}")
        raise


def parse_page(html: str) -> List[Dict[str, Optional[str]]]:
    """
    Парсит одну страницу каталога и возвращает список словарей с сырыми данными.
    """
    try:
        soup = BeautifulSoup(html, "html.parser")
        book_articles = soup.select("article.product_pod")
        logger.info(f"[EXTRACT] Найдено элементов на странице: {len(book_articles)}")

        records = []
        for article in book_articles:
            # Название книги
            title = article.h3.a["title"]

            # Цена (сырая строка, например "£51.77")
            price_raw = article.select_one("p.price_color").get_text(strip=True)

            # Рейтинг (класс вида "star-rating Three")
            rating_classes = article.select_one("p.star-rating")["class"]
            rating_word = [c for c in rating_classes if c != "star-rating"][0]

            # Наличие (текст внутри <p class="instock availability">)
            availability = article.select_one("p.instock.availability").get_text(strip=True)
            availability = " ".join(availability.split())  # нормализация пробелов

            # Ссылка на детальную страницу
            detail_href = article.h3.a["href"]
            detail_url = f"{BASE_URL}catalogue/{detail_href}"

            records.append({
                "title": title,
                "price_raw": price_raw,
                "rating_word": rating_word,
                "availability": availability,
                "detail_url": detail_url,
                "scraped_at": datetime.now().isoformat(),
            })

        return records

    except Exception as e:
        logger.error(f"[EXTRACT] Ошибка парсинга DOM: {e}")
        raise


def get_total_pages(html: str) -> int:
    """
    Определяет общее количество страниц из блока пагинации.
    """
    try:
        soup = BeautifulSoup(html, "html.parser")
        pager = soup.select_one("ul.pager li.current")
        if pager:
            match = re.search(r"of\s+(\d+)", pager.get_text(strip=True))
            if match:
                return int(match.group(1))
        return 1
    except Exception as e:
        logger.warning(f"[EXTRACT] Не удалось определить пагинацию: {e}")
        return 1


def extract_all_pages() -> List[Dict[str, Optional[str]]]:
    """
    Orchestrator: обходит все страницы каталога и агрегирует данные.
    """
    all_data: List[Dict[str, Optional[str]]] = []

    # --- Первая страница ---
    first_html = fetch_html(BASE_URL)
    all_data.extend(parse_page(first_html))

    total_pages = get_total_pages(first_html)
    logger.info(f"[EXTRACT] Всего страниц для обхода: {total_pages}")

    # --- Остальные страницы ---
    for page_num in range(2, total_pages + 1):
        page_url = f"{BASE_URL}catalogue/page-{page_num}.html"
        try:
            html = fetch_html(page_url)
            page_data = parse_page(html)
            all_data.extend(page_data)
            logger.info(
                f"[EXTRACT] Страница {page_num}/{total_pages} готова. "
                f"Всего записей: {len(all_data)}"
            )
        except Exception as e:
            logger.error(f"[EXTRACT] Пропуск страницы {page_num} из-за ошибки: {e}")
            continue

    logger.info(f"[EXTRACT] Сбор данных завершён. Всего записей: {len(all_data)}")
    return all_data


# =============================================================================
# TRANSFORM & LOAD
# =============================================================================
def clean_and_save(records: List[Dict[str, Optional[str]]]) -> None:
    """
    Очищает данные с помощью pandas и сохраняет в CSV и Excel.
    """
    if not records:
        logger.warning("[TRANSFORM] Нет данных для обработки")
        return

    try:
        logger.info("[TRANSFORM] Начало очистки данных...")
        df = pd.DataFrame(records)

        # --- Анализ качества до очистки ---
        missing_before = df.isnull().sum().sum()
        logger.info(f"[TRANSFORM] Пустых значений (до): {missing_before}")

        # --- Удаление дубликатов по названию + цене ---
        rows_before = len(df)
        df = df.drop_duplicates(subset=["title", "price_raw"], keep="first")
        logger.info(f"[TRANSFORM] Удалено дубликатов: {rows_before - len(df)}")

        # --- Очистка цены: удаление символа £ и конвертация в float ---
        df["price"] = (
            df["price_raw"]
            .str.replace(r"[£$€]", "", regex=True)
            .str.strip()
            .astype(float)
        )

        # --- Обработка некорректных цен ---
        invalid_prices = df["price"].isnull().sum()
        if invalid_prices:
            logger.warning(f"[TRANSFORM] Некорректных цен: {invalid_prices} — удаляем")
            df = df.dropna(subset=["price"])

        # --- Конвертация рейтинга: слово -> число ---
        df["rating"] = df["rating_word"].map(RATING_MAP)

        # --- Обработка пустых рейтингов (если встретится неизвестный класс) ---
        df["rating"] = df["rating"].fillna(0).astype(int)

        # --- Финальный выбор колонок ---
        df_clean = df[[
            "title",
            "price",
            "rating",
            "availability",
            "detail_url",
            "scraped_at",
        ]].copy()

        # --- Сортировка ---
        df_clean = df_clean.sort_values(by="price", ascending=True).reset_index(drop=True)

        logger.info(f"[TRANSFORM] Очистка завершена. Итоговых записей: {len(df_clean)}")

        # --- LOAD ---
        os.makedirs(OUTPUT_DIR, exist_ok=True)

        # CSV
        df_clean.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")
        logger.info(f"[LOAD] Сохранено в CSV: {OUTPUT_CSV}")

        # Excel
        df_clean.to_excel(OUTPUT_XLSX, index=False, engine="openpyxl")
        logger.info(f"[LOAD] Сохранено в Excel: {OUTPUT_XLSX}")

        # --- Статистика для интервьюера ---
        logger.info("=" * 50)
        logger.info("СТАТИСТИКА СКРЕЙПИНГА")
        logger.info(f"Всего книг:        {len(df_clean)}")
        logger.info(f"Средняя цена:      £{df_clean['price'].mean():.2f}")
        logger.info(f"Медианный рейтинг: {df_clean['rating'].median()}")
        logger.info("Топ-3 по цене:")
        for _, row in df_clean.nlargest(3, "price").iterrows():
            logger.info(f"  • {row['title'][:50]}... — £{row['price']:.2f}")
        logger.info("=" * 50)

    except Exception as e:
        logger.error(f"[TRANSFORM/LOAD] Ошибка: {e}")
        raise


# =============================================================================
# MAIN
# =============================================================================
def main() -> int:
    """
    Главная точка входа. Оркестрирует полный ETL-цикл.
    """
    logger.info("=" * 50)
    logger.info("EY DATA SCRAPING AUTOMATION — ETL START")
    logger.info("=" * 50)

    try:
        # 1. EXTRACT
        raw_data = extract_all_pages()

        # 2. TRANSFORM & LOAD
        clean_and_save(raw_data)

        logger.info("ETL-процесс успешно завершён!")
        return 0

    except Exception as e:
        logger.critical(f"Критический сбой ETL: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
