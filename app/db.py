import sqlite3
from flask import current_app, g
from werkzeug.security import generate_password_hash


def get_db_connection():
    """
    Establishes a database connection.
    Uses Flask's 'g' object to cache the connection throughout the request,
    ensuring a single connection per request.
    """
    if 'db' not in g:
        database = current_app.config.get('DATABASE')
        if not database:
            raise RuntimeError("Environment variable 'DATABASE' is not set. Check your .env file.")
        conn = sqlite3.connect(database)
        conn.row_factory = sqlite3.Row
        g.db = conn
    return g.db


def close_connection(exception):
    """Closes the database connection after the request is complete."""
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()


def init_db():
    """
    Initializes the database: creates necessary tables (users, products, cart_items, favorite_items, reviews)
    and adds initial data (administrator, flowers) if they don't exist.
    """
    db = get_db_connection()
    cursor = db.cursor()

    # Create the users table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'user'
            )
        ''')
    db.commit()

    # Create the products table
    # Added 'stock' column with a default value.
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            price REAL NOT NULL,
            image_url TEXT,
            stock INTEGER NOT NULL DEFAULT 100 -- New stock column
        )
    ''')

    # Create the cart_items table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS cart_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            flower_id INTEGER NOT NULL,
            quantity INTEGER NOT NULL,
            UNIQUE(user_id, flower_id),
            FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
            FOREIGN KEY (flower_id) REFERENCES products (id) ON DELETE CASCADE
        )
    ''')

    # Create the favorite_items table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS favorite_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            flower_id INTEGER NOT NULL,
            UNIQUE(user_id, flower_id),
            FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
            FOREIGN KEY (flower_id) REFERENCES products (id) ON DELETE CASCADE
        )
    ''')

    # New reviews table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            rating INTEGER NOT NULL, -- Rating from 1 to 5
            comment TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (product_id) REFERENCES products (id) ON DELETE CASCADE,
            FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
            CONSTRAINT check_rating CHECK (rating >= 1 AND rating <= 5)
        )
    ''')

    # New orders table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            total_amount REAL NOT NULL,
            status TEXT NOT NULL DEFAULT 'Очікується', -- 'Очікується', 'Підтверджено'
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
        )
    ''')

    # New order_items table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS order_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL,
            flower_id INTEGER NOT NULL,
            quantity INTEGER NOT NULL,
            price_at_purchase REAL NOT NULL, -- Price at the time of purchase
            FOREIGN KEY (order_id) REFERENCES orders (id) ON DELETE CASCADE,
            FOREIGN KEY (flower_id) REFERENCES products (id) ON DELETE CASCADE
        )
    ''')

    db.commit()

    # Check if the default administrator exists, and add if not
    cursor.execute("SELECT COUNT(*) FROM users WHERE username = 'admin'")
    if cursor.fetchone()[0] == 0:
        hashed_password = generate_password_hash('admin123')
        cursor.execute("INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                       ('admin', hashed_password, 'admin'))
        db.commit()
        print("Default administrator added (login: admin, password: admin123)")

    # Check if initial products exist, and add if not
    cursor.execute("SELECT COUNT(*) FROM products")
    if cursor.fetchone()[0] == 0:
        initial_flowers_data = [
            {
                'name': 'Троянда червона',
                'description': 'Класична червона троянда – символ любові.',
                'price': 150,
                'image_url': 'static/images/flower1.jpg',
                'stock': 50 # Initial stock
            },
            {
                'name': 'Тюльпан жовтий',
                'description': 'Яскравий тюльпан для гарного настрою.',
                'price': 90,
                'image_url': 'static/images/flower2.jpg',
                'stock': 75 # Initial stock
            },
            {
                'name': 'Лілія біла',
                'description': 'Ніжна біла лілія – вишуканий подарунок.',
                'price': 120,
                'image_url': 'static/images/flower3.jpg',
                'stock': 30 # Initial stock
            },
            {
                'name': 'Ромашка',
                'description': 'Світла та ніжна ромашка – символ чистоти.',
                'price': 80,
                'image_url': 'static/images/flower4.jpg',
                'stock': 100 # Initial stock
            },
            {
                'name': 'Гвоздика',
                'description': 'Яскрава гвоздика – чудовий подарунок.',
                'price': 95,
                'image_url': 'static/images/flower5.jpeg',
                'stock': 60 # Initial stock
            },
            {
                'name': 'Астра',
                'description': 'Різнобарвна астра додасть настрою.',
                'price': 85,
                'image_url': 'static/images/flower6.jpg',
                'stock': 45 # Initial stock
            },
            {
                'name': 'Незабутка',
                'description': 'Маленька незабутка – символ пам’яті.',
                'price': 70,
                'image_url': 'static/images/flower7.jpg',
                'stock': 80 # Initial stock
            },
            {
                'name': 'Гладіолус',
                'description': 'Вишуканий гладіолус для особливих моментів.',
                'price': 110,
                'image_url': 'static/images/flower8.jpg',
                'stock': 25 # Initial stock
            },
            {
                'name': 'Нарцис',
                'description': 'Весняний нарцис – передвісник тепла.',
                'price': 90,
                'image_url': 'static/images/flower9.jpg',
                'stock': 90 # Initial stock
            },
            {
                'name': 'Крокус',
                'description': 'Перший весняний крокус – надія і радість.',
                'price': 75,
                'image_url': 'static/images/flower10.jpg',
                'stock': 120 # Initial stock
            },
            {
                'name': 'Гербера',
                'description': 'Яскрава гербера – посмішка в кожен день.',
                'price': 100,
                'image_url': 'static/images/flower11.jpg',
                'stock': 70 # Initial stock
            },
        ]
        for flower in initial_flowers_data:
            cursor.execute("INSERT INTO products (name, description, price, image_url, stock) VALUES (?, ?, ?, ?, ?)",
                           (flower['name'], flower['description'], flower['price'], flower['image_url'], flower['stock']))
        db.commit()
        print("Initial flowers added to the database.")

    print("Database initialized.")
