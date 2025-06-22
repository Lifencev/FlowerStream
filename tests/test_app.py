import os
import sqlite3
import datetime
import pytest

from app.app import (
    app,
    load_products_from_db,
    get_reviews_for_product,
    get_average_rating_for_product,
    load_user_cart_from_db,
    save_user_cart_to_db,
    load_user_favorites_from_db,
    save_user_favorites_to_db, get_flower_by_id, format_date,
)

@pytest.fixture(autouse=True)
def patch_db(monkeypatch, tmp_path):
    db_file = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_file))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            description TEXT,
            price REAL,
            image_url TEXT,
            stock INTEGER
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password_hash TEXT,
            role TEXT
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER,
            user_id INTEGER,
            rating INTEGER,
            comment TEXT,
            created_at TEXT
        )
        """
    )
    cursor.execute(
        "CREATE TABLE cart_items (user_id INTEGER, flower_id INTEGER, quantity INTEGER)"
    )
    cursor.execute(
        "CREATE TABLE favorite_items (user_id INTEGER, flower_id INTEGER)"
    )
    conn.commit()
    # Monkeypatch the database connection in the app module
    monkeypatch.setattr('app.app.get_db_connection', lambda: conn)
    return conn

@pytest.fixture
def client(patch_db):
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client


def test_load_products_from_db_empty():
    products = load_products_from_db()
    assert products == []


def test_load_products_from_db_search_and_sort(patch_db):
    conn = patch_db
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO products (name, description, price, image_url, stock) VALUES (?, ?, ?, ?, ?)",
        ("Rose", "Red rose", 10.0, None, 5)
    )
    cursor.execute(
        "INSERT INTO products (name, description, price, image_url, stock) VALUES (?, ?, ?, ?, ?)",
        ("Tulip", "Yellow tulip", 5.0, None, 3)
    )
    conn.commit()
    products = load_products_from_db()
    assert [p['name'] for p in products] == ['Rose', 'Tulip']
    products = load_products_from_db(sort_order='price_desc')
    assert [p['name'] for p in products] == ['Rose', 'Tulip']
    products = load_products_from_db(search_term='yellow')
    assert [p['name'] for p in products] == ['Tulip']


def test_get_flower_data_route(client, patch_db):
    conn = patch_db
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO products (name, description, price, image_url, stock) VALUES (?, ?, ?, ?, ?)",
        ("Daisy", "White daisy", 7.5, "static/images/daisy.jpg", 10)
    )
    conn.commit()
    response = client.get('/get_flower_data/1')
    assert response.status_code == 200
    data = response.get_json()
    assert data['name'] == 'Daisy'
    response = client.get('/get_flower_data/999')
    assert response.status_code == 404


def test_get_reviews_and_average_rating(patch_db):
    conn = patch_db
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO products (name, description, price, image_url, stock) VALUES (?, ?, ?, ?, ?)",
        ("Krokus", "", 8.0, None, 2)
    )
    cursor.execute(
        "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
        ("user1", "hash", "user")
    )
    utc1 = "2025-01-01 00:00:00"
    utc2 = "2025-01-02 12:30:00"
    cursor.execute(
        "INSERT INTO reviews (product_id, user_id, rating, comment, created_at) VALUES (?, ?, ?, ?, ?)",
        (1, 1, 4, "Nice", utc1)
    )
    cursor.execute(
        "INSERT INTO reviews (product_id, user_id, rating, comment, created_at) VALUES (?, ?, ?, ?, ?)",
        (1, 1, 2, "Okay", utc2)
    )
    conn.commit()
    reviews = get_reviews_for_product(1)
    assert reviews[0]['rating'] == 2
    assert reviews[0]['created_at'] == "2025-01-02 15:30:00"
    avg = get_average_rating_for_product(1)
    assert avg == 3.0


def test_cart_and_favorites(patch_db):
    conn = patch_db
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
        ("user2", "hash", "user")
    )
    cursor.execute(
        "INSERT INTO products (name, description, price, image_url, stock) VALUES (?, ?, ?, ?, ?)",
        ("Orchid", "", 12.0, None, 4)
    )
    conn.commit()
    assert load_user_cart_from_db(1) == []
    save_user_cart_to_db(1, [{'id': 1, 'quantity': 2}])
    cart = load_user_cart_from_db(1)
    assert len(cart) == 1 and cart[0]['id'] == 1 and cart[0]['quantity'] == 2
    assert load_user_favorites_from_db(1) == []
    save_user_favorites_to_db(1, [{'id': 1}])
    favs = load_user_favorites_from_db(1)
    assert len(favs) == 1 and favs[0]['id'] == 1



def test_get_flower_by_id_valid(patch_db):
    conn = patch_db
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO products (name, description, price, image_url, stock) VALUES (?, ?, ?, ?, ?)",
        ("Sunflower", "Bright", 3.0, None, 7)
    )
    conn.commit()
    flower = get_flower_by_id(1)
    assert flower is not None
    assert flower['name'] == "Sunflower"
    assert flower['stock'] == 7


def test_get_flower_by_id_invalid(patch_db):
    assert get_flower_by_id(999) is None


def test_format_date_datetime_object():
    dt = datetime.datetime(2021, 12, 31, 23, 59, 59)
    assert format_date(dt, "%d/%m/%Y") == "31/12/2021"


def test_format_date_string_input():
    value = "2025-01-01 08:00:00"
    assert format_date(value, "%Y-%m-%d") == "2025-01-01"


def test_format_date_invalid_input():
    assert format_date("not a date", "%Y") == "not a date"


def test_average_rating_no_reviews(patch_db):
    conn = patch_db
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO products (name, description, price, image_url, stock) VALUES (?, ?, ?, ?, ?)",
        ("Orchid", "", 12.0, None, 4)
    )
    conn.commit()
    assert get_average_rating_for_product(1) == 0.0


def test_save_user_cart_overwrites(patch_db):
    conn = patch_db
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO products (name, description, price, image_url, stock) VALUES (?, ?, ?, ?, ?)",
        ("Iris", "", 6.0, None, 2)
    )
    conn.commit()
    save_user_cart_to_db(1, [{'id': 1, 'quantity': 1}])
    save_user_cart_to_db(1, [{'id': 1, 'quantity': 5}])
    cart = load_user_cart_from_db(1)
    assert len(cart) == 1
    assert cart[0]['quantity'] == 5


def test_save_user_favorites_overwrites(patch_db):
    conn = patch_db
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)"
    ,   ("favuser", "hash", "user"))
    cursor.execute(
        "INSERT INTO products (name, description, price, image_url, stock) VALUES (?, ?, ?, ?, ?)",
        ("Peony", "", 9.0, None, 3)
    )
    conn.commit()
    save_user_favorites_to_db(1, [{'id': 1}])
    save_user_favorites_to_db(1, [])
    favs = load_user_favorites_from_db(1)
    assert favs == []


def test_load_products_sort_newest(patch_db):
    conn = patch_db
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO products (name, description, price, image_url, stock) VALUES (?, ?, ?, ?, ?)",
        ("A", "", 1.0, None, 1)
    )
    cursor.execute(
        "INSERT INTO products (name, description, price, image_url, stock) VALUES (?, ?, ?, ?, ?)",
        ("B", "", 2.0, None, 2)
    )
    conn.commit()
    products = load_products_from_db(sort_order='newest')
    assert [p['name'] for p in products] == ['B', 'A']



def test_load_products_sort_price_asc(patch_db):
    conn = patch_db
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO products (name, description, price, image_url, stock) VALUES (?, ?, ?, ?, ?)",
        ("Cheap", "", 1.0, None, 10)
    )
    cursor.execute(
        "INSERT INTO products (name, description, price, image_url, stock) VALUES (?, ?, ?, ?, ?)",
        ("Expensive", "", 100.0, None, 5)
    )
    conn.commit()
    products = load_products_from_db(sort_order='price_asc')
    assert [p['price'] for p in products] == [1.0, 100.0]


def test_load_products_sort_name_desc(patch_db):
    conn = patch_db
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO products (name, description, price, image_url, stock) VALUES (?, ?, ?, ?, ?)",
        ("Alpha", "", 1.0, None, 1)
    )
    cursor.execute(
        "INSERT INTO products (name, description, price, image_url, stock) VALUES (?, ?, ?, ?, ?)",
        ("Beta", "", 2.0, None, 1)
    )
    conn.commit()
    products = load_products_from_db(sort_order='name_desc')
    assert [p['name'] for p in products] == ['Beta', 'Alpha']


def test_load_products_sort_oldest(patch_db):
    conn = patch_db
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO products (name, description, price, image_url, stock) VALUES (?, ?, ?, ?, ?)",
        ("First", "", 1.0, None, 1)
    )
    cursor.execute(
        "INSERT INTO products (name, description, price, image_url, stock) VALUES (?, ?, ?, ?, ?)",
        ("Second", "", 2.0, None, 2)
    )
    conn.commit()
    products = load_products_from_db(sort_order='oldest')
    assert [p['name'] for p in products] == ['First', 'Second']


def test_load_products_case_insensitive_search(patch_db):
    conn = patch_db
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO products (name, description, price, image_url, stock) VALUES (?, ?, ?, ?, ?)",
        ("MiXeD", "CaSe", 1.0, None, 1)
    )
    conn.commit()
    products_lower = load_products_from_db(search_term='mixed')
    products_upper = load_products_from_db(search_term='MIXED')
    assert len(products_lower) == 1
    assert len(products_upper) == 1


def test_load_user_cart_multiple_items(patch_db):
    conn = patch_db
    cursor = conn.cursor()
    # Insert products
    cursor.execute(
        "INSERT INTO products (name, description, price, image_url, stock) VALUES (?, ?, ?, ?, ?)",
        ("One", "", 1.0, None, 1)
    )
    cursor.execute(
        "INSERT INTO products (name, description, price, image_url, stock) VALUES (?, ?, ?, ?, ?)",
        ("Two", "", 2.0, None, 2)
    )
    conn.commit()
    save_user_cart_to_db(1, [{'id': 1, 'quantity': 1}, {'id': 2, 'quantity': 2}])
    cart = load_user_cart_from_db(1)
    assert len(cart) == 2
    assert {item['id'] for item in cart} == {1, 2}


def test_load_user_favorites_multiple_items(patch_db):
    conn = patch_db
    cursor = conn.cursor()
    # Insert user and products
    cursor.execute(
        "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
        ("favuser2", "hash", "user")
    )
    cursor.execute(
        "INSERT INTO products (name, description, price, image_url, stock) VALUES (?, ?, ?, ?, ?)",
        ("FavOne", "", 1.0, None, 1)
    )
    cursor.execute(
        "INSERT INTO products (name, description, price, image_url, stock) VALUES (?, ?, ?, ?, ?)",
        ("FavTwo", "", 2.0, None, 2)
    )
    conn.commit()
    save_user_favorites_to_db(1, [{'id': 1}, {'id': 2}])
    favs = load_user_favorites_from_db(1)
    assert len(favs) == 2
    assert {f['id'] for f in favs} == {1, 2}


def test_get_reviews_for_product_no_reviews(patch_db):
    assert get_reviews_for_product(1) == []