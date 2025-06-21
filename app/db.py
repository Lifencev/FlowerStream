import sqlite3
from flask import current_app, g
from werkzeug.security import generate_password_hash


def get_db_connection():
    """
    Establishes a database connection using Flask's `g` for caching.
    Reads the DATABASE path from app config.
    """
    if 'db' not in g:
        database = current_app.config.get('DATABASE')
        if not database:
            raise RuntimeError("Environment variable 'DATABASE' is not set. Check your .env file.")
        conn = sqlite3.connect(database)
        conn.row_factory = sqlite3.Row
        g.db = conn
    return g.db


def close_connection(exception=None):
    """
    Closes the database connection at the end of the request, if it exists.
    """
    db = g.pop('db', None)
    if db is not None:
        db.close()


def init_db():
    """
    Initializes the database:
      - Creates tables: users, products, cart_items, favorite_items, reviews
      - Seeds default administrator and initial products if they don't exist
    """
    db = get_db_connection()
    cursor = db.cursor()

    # --- Create tables ---
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'user'
    )''')
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        description TEXT,
        price REAL NOT NULL,
        image_url TEXT
    )''')
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS cart_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        flower_id INTEGER NOT NULL,
        quantity INTEGER NOT NULL DEFAULT 1,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
        FOREIGN KEY (flower_id) REFERENCES products(id) ON DELETE CASCADE
    )''')
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS favorite_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        flower_id INTEGER NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
        FOREIGN KEY (flower_id) REFERENCES products(id) ON DELETE CASCADE
    )''')
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS reviews (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        product_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        rating INTEGER NOT NULL CHECK (rating >= 1 AND rating <= 5),
        comment TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    )''')
    db.commit()

    # --- Seed default administrator ---
    cursor.execute("SELECT COUNT(*) FROM users WHERE username = ?", ('admin',))
    if cursor.fetchone()[0] == 0:
        hashed_password = generate_password_hash('admin123')
        cursor.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
            ('admin', hashed_password, 'admin')
        )
        db.commit()
        print("Default administrator added (login: admin, password: admin123)")

    # --- Seed initial products ---
    cursor.execute("SELECT COUNT(*) FROM products")
    if cursor.fetchone()[0] == 0:
        initial_flowers = [
            {'name': 'Троянда червона',    'description': 'Класична червона троянда – символ любові.',   'price': 150, 'image_url': 'static/images/flower1.jpg'},
            {'name': 'Тюльпан жовтий',     'description': 'Яскравий тюльпан для гарного настрою.',      'price': 90,  'image_url': 'static/images/flower2.jpg'},
            {'name': 'Лілія біла',        'description': 'Ніжна біла лілія – вишуканий подарунок.',    'price': 120, 'image_url': 'static/images/flower3.jpg'},
            {'name': 'Орхідея фіолетова','description': 'Екзотична фіолетова орхідея для цінителів.', 'price': 200, 'image_url': 'static/images/flower4.jpg'},
            {'name': 'Піон рожевий',     'description': 'Пишний рожевий півонія – ніжність та краса.', 'price': 180, 'image_url': 'static/images/flower5.jpg'},
            {'name': 'Гвоздика',         'description': 'Ароматна гвоздика – чудовий додаток до букету.', 'price': 80,  'image_url': 'static/images/flower6.jpg'},
            {'name': 'Астра',            'description': 'Кольорова астра – яскравий акцент у вашому домі.', 'price': 60,  'image_url': 'static/images/flower7.jpg'},
            {'name': 'Нарцис',           'description': 'Весняний нарцис – символ оновлення.',         'price': 70,  'image_url': 'static/images/flower8.jpg'},
            {'name': 'Іриси',            'description': 'Елегантні іриси – витонченість та стиль.',      'price': 90,  'image_url': 'static/images/flower9.jpg'},
            {'name': 'Крокус',           'description': 'Перший весняний крокус – надія і радість.',    'price': 75,  'image_url': 'static/images/flower10.jpg'},
            {'name': 'Гербера',          'description': 'Яскрава гербера – посмішка в кожен день.',     'price': 100, 'image_url': 'static/images/flower11.jpg'},
        ]
        for flower in initial_flowers:
            cursor.execute(
                "INSERT INTO products (name, description, price, image_url) VALUES (?, ?, ?, ?)",
                (flower['name'], flower['description'], flower['price'], flower['image_url'])
            )
        db.commit()
        print("Initial flowers added to the database.")

    print("Database initialized.")
