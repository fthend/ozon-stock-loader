import os
from dotenv import load_dotenv
import requests
import pandas as pd
import mysql.connector
from mysql.connector import Error

load_dotenv()

# CONFIG
OZON_CLIENTS = {
    "Кутуев": [
        {
            "client_id": "2266084",
            "api_key": "6c7ded11-f31d-426a-ac5a-52883dbc65ff"
        }
    ]
}

DB_CONFIG = {
    "host": os.getenv("DB_HOST"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "database": os.getenv("DB_NAME"),
    "port": int(os.getenv("DB_PORT"))
}


URL = "https://api-seller.ozon.ru/v2/analytics/stock_on_warehouses"
PAGE_SIZE = 100


# API REQUEST
def get_ozon_data(client_id, api_key, limit=100, offset=0):
    headers = {
        "Client-Id": client_id,
        "Api-Key": api_key,
        "Content-Type": "application/json"
    }

    payload = {
        "limit": limit,
        "offset": offset,
        "warehouse_type": "ALL"
    }

    try:
        response = requests.post(URL, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"Ошибка API: {e}")
        return None


# Преобразование в датафрейм
def transform_to_dataframe(rows):
    try:
        if not rows:
            return pd.DataFrame()

        df = pd.DataFrame(rows)
        print(df.head(3))

        return df

    except Exception as e:
        print(f"Ошибка преобразования: {e}")
        return pd.DataFrame()


# Сохранение в БД
def save_to_db_from_dataframe(df):
    if df.empty:
        print("DataFrame пуст, вставка пропущена")
        return 0

    connection = None

    try:
        connection = mysql.connector.connect(**DB_CONFIG)
        cursor = connection.cursor()

        # Создание таблицы
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS ozon_stocks (
            id INT AUTO_INCREMENT PRIMARY KEY,
            sku BIGINT,
            item_code VARCHAR(255),
            item_name VARCHAR(500),
            warehouse_name VARCHAR(255),
            free_to_sell_amount INT,
            reserved_amount INT,
            promised_amount INT
        )
        """)

        query = """
        INSERT INTO ozon_stocks (
            sku, item_code, item_name, warehouse_name,
            free_to_sell_amount, reserved_amount, promised_amount
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """

        data = [
            (
                row.get("sku"),
                row.get("item_code"),
                row.get("item_name"),
                row.get("warehouse_name"),
                row.get("free_to_sell_amount", 0),
                row.get("reserved_amount", 0),
                row.get("promised_amount", 0)
            )
            for _, row in df.iterrows()
        ]

        cursor.executemany(query, data)
        connection.commit()

        print(f"Сохранено записей: {cursor.rowcount}")
        return cursor.rowcount

    except Error as e:
        print(f"Ошибка БД: {e}")
        if connection:
            connection.rollback()
        return 0

    finally:
        if connection and connection.is_connected():
            cursor.close()
            connection.close()


# Обработка данных для клиента
def process_client(client_id, api_key):
    offset = 0
    total_saved = 0

    while True:
        print(f"\nЗапрос (offset={offset})")

        data = get_ozon_data(client_id, api_key, PAGE_SIZE, offset)

        if not data:
            break

        rows = data.get("result", {}).get("rows", [])

        if not rows:
            break

        df = transform_to_dataframe(rows)

        saved = save_to_db_from_dataframe(df)
        total_saved += saved

        if len(rows) < PAGE_SIZE:
            break

        offset += PAGE_SIZE

    print(f"Всего сохранено: {total_saved}")



# MAIN
def main():
    for client_name, keys in OZON_CLIENTS.items():
        print(f"\nКлиент: {client_name}")

        for key in keys:
            client_id = key["client_id"]
            api_key = key["api_key"]

            process_client(client_id, api_key)

    print("\nОбработка завершена")


if __name__ == "__main__":
    main()
