from flask import Flask, render_template, request, redirect, url_for, flash, session, g, jsonify
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
import datetime
import os
import stripe
from config import Config
from dotenv import load_dotenv, find_dotenv
from werkzeug.utils import secure_filename
import uuid # Import uuid for generating unique filenames and reset tokens

load_dotenv(find_dotenv())

import requests

def get_uah_to_eur_rate():
    try:
        response = requests.get("https://bank.gov.ua/NBUStatService/v1/statdirectory/exchange?valcode=EUR&json")
        data = response.json()
        rate = float(data[0]['rate'])
        return rate
    except Exception as e:
        print(f"Не вдалося отримати курс НБУ: {e}")
        return 50.0  # extra price in case of error of getting rate


app = Flask(__name__)
app.config.from_object(Config)
stripe.api_key = app.config['STRIPE_SECRET_KEY']
DATABASE = os.getenv('DATABASE')

# --- File upload settings ---
UPLOAD_FOLDER = 'static/images'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

full_upload_path = os.path.join(app.root_path, UPLOAD_FOLDER)
if not os.path.exists(full_upload_path):
    try:
        os.makedirs(full_upload_path)
        print(f"Upload folder created: {full_upload_path}")
    except OSError as e:
        print(f"Error creating upload folder {full_upload_path}: {e}")
        flash(f"Server error: failed to create upload folder. {e}", "danger")


def allowed_file(filename):
    """
    Checks if the file extension is allowed.
    """
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def get_db_connection():
    """
    Establishes a database connection.
    Uses Flask's 'g' object to cache the connection throughout the request.
    """
    db = getattr(g, '_database', None)
    if db is None:
        if DATABASE is None:
            raise RuntimeError("Environment variable 'DATABASE' is not set. Check your .env file.")
        db = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db


@app.teardown_appcontext
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
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            price REAL NOT NULL,
            image_url TEXT
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


    db.commit()

    # Check if the default administrator exists
    cursor.execute("SELECT COUNT(*) FROM users WHERE username = 'admin'")
    if cursor.fetchone()[0] == 0:
        hashed_password = generate_password_hash('admin123')
        cursor.execute("INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                       ('admin', hashed_password, 'admin'))
        db.commit()
        print("Default administrator added (login: admin, password: admin123)")

    cursor.execute("SELECT COUNT(*) FROM products")
    if cursor.fetchone()[0] == 0:
        initial_flowers_data = [
            {
                'name': 'Троянда червона',
                'description': 'Класична червона троянда – символ любові.',
                'price': 150,
                'image_url': 'static/images/flower1.jpg'
            },
            {
                'name': 'Тюльпан жовтий',
                'description': 'Яскравий тюльпан для гарного настрою.',
                'price': 90,
                'image_url': 'static/images/flower2.jpg'
            },
            {
                'name': 'Лілія біла',
                'description': 'Ніжна біла лілія – вишуканий подарунок.',
                'price': 120,
                'image_url': 'static/images/flower3.jpg'
            },
            {
                'name': 'Ромашка',
                'description': 'Світла та ніжна ромашка – символ чистоти.',
                'price': 80,
                'image_url': 'static/images/flower4.jpg'
            },
            {
                'name': 'Гвоздика',
                'description': 'Яскрава гвоздика – чудовий подарунок.',
                'price': 95,
                'image_url': 'static/images/flower5.jpeg'
            },
            {
                'name': 'Астра',
                'description': 'Різнобарвна астра додасть настрою.',
                'price': 85,
                'image_url': 'static/images/flower6.jpg'
            },
            {
                'name': 'Незабутка',
                'description': 'Маленька незабутка – символ пам’яті.',
                'price': 70,
                'image_url': 'static/images/flower7.jpg'
            },
            {
                'name': 'Гладіолус',
                'description': 'Вишуканий гладіолус для особливих моментів.',
                'price': 110,
                'image_url': 'static/images/flower8.jpg'
            },
            {
                'name': 'Нарцис',
                'description': 'Весняний нарцис – передвісник тепла.',
                'price': 90,
                'image_url': 'static/images/flower9.jpg'
            },
            {
                'name': 'Крокус',
                'description': 'Перший весняний крокус – надія і радість.',
                'price': 75,
                'image_url': 'static/images/flower10.jpg'
            },
            {
                'name': 'Гербера',
                'description': 'Яскрава гербера – посмішка в кожен день.',
                'price': 100,
                'image_url': 'static/images/flower11.jpg'
            },
        ]
        for flower in initial_flowers_data:
            cursor.execute("INSERT INTO products (name, description, price, image_url) VALUES (?, ?, ?, ?)",
                           (flower['name'], flower['description'], flower['price'], flower['image_url']))
        db.commit()
        print("Initial flowers added to the database.")

    print("Database initialized.")

with app.app_context():
    init_db()


def load_products_from_db(search_term=None, sort_order=None):
    """
    Loads all products (flowers) from the products table.
    If search_term is provided, filters products by name or description.
    """
    db = get_db_connection()
    cursor = db.cursor()

    base_query = "SELECT * FROM products"
    conditions = []
    params = []

    if search_term:
        conditions.append("(name LIKE ? OR description LIKE ?)")
        search_pattern = f"%{search_term}%"
        params.extend([search_pattern, search_pattern])

    if conditions:
        base_query += " WHERE " + " AND ".join(conditions)

    # Sorting
    if sort_order == 'price_asc':
        base_query += " ORDER BY price ASC"
    elif sort_order == 'price_desc':
        base_query += " ORDER BY price DESC"
    else:
        base_query += " ORDER BY id ASC"

    cursor.execute(base_query, params)
    return cursor.fetchall()


def get_reviews_for_product(product_id):
    """Returns all reviews for a specific product."""
    db = get_db_connection()
    cursor = db.execute("""
        SELECT r.id, r.rating, r.comment, r.created_at, u.username
        FROM reviews r
        JOIN users u ON r.user_id = u.id
        WHERE r.product_id = ?
        ORDER BY r.created_at DESC
    """, (product_id,))
    return cursor.fetchall()


def get_flower_by_id(flower_id):
    """Returns a flower object by ID from the DB."""
    db = get_db_connection()
    cursor = db.execute("SELECT * FROM products WHERE id = ?", (flower_id,))
    return cursor.fetchone()


def get_average_rating_for_product(product_id):
    """Calculates the average rating for a specific product."""
    db = get_db_connection()
    cursor = db.execute("SELECT AVG(rating) FROM reviews WHERE product_id = ?", (product_id,))
    avg_rating = cursor.fetchone()[0]
    return round(avg_rating, 2) if avg_rating else 0.0


def load_user_cart_from_db(user_id):
    """Loads user's cart from DB and returns it in session format."""
    db = get_db_connection()
    cursor = db.execute("""
        SELECT ci.quantity, p.id, p.name, p.description, p.price, p.image_url
        FROM cart_items ci
        JOIN products p ON ci.flower_id = p.id
        WHERE ci.user_id = ?
    """, (user_id,))
    cart_data = []
    for row in cursor.fetchall():
        item = {
            'id': row['id'],
            'name': row['name'],
            'description': row['description'],
            'price': row['price'],
            'image_url': row['image_url'],
            'quantity': row['quantity']
        }
        cart_data.append(item)
    return cart_data

def save_user_cart_to_db(user_id, cart_data):
    """Saves user's cart from session to DB."""
    db = get_db_connection()
    cursor = db.cursor()
    cursor.execute("DELETE FROM cart_items WHERE user_id = ?", (user_id,))
    for item in cart_data:
        cursor.execute("INSERT INTO cart_items (user_id, flower_id, quantity) VALUES (?, ?, ?)",
                       (user_id, item['id'], item['quantity']))
    db.commit()

def load_user_favorites_from_db(user_id):
    """Loads user's favorites from DB and returns it in session format."""
    db = get_db_connection()
    cursor = db.execute("""
        SELECT p.id, p.name, p.description, p.price, p.image_url
        FROM favorite_items fi
        JOIN products p ON fi.flower_id = p.id
        WHERE fi.user_id = ?
    """, (user_id,))
    favorites_data = []
    for row in cursor.fetchall():
        item = {
            'id': row['id'],
            'name': row['name'],
            'description': row['description'],
            'price': row['price'],
            'image_url': row['image_url'],
        }
        favorites_data.append(item)
    return favorites_data

def save_user_favorites_to_db(user_id, favorites_data):
    """Saves user's favorites from session to DB."""
    db = get_db_connection()
    cursor = db.cursor()
    cursor.execute("DELETE FROM favorite_items WHERE user_id = ?", (user_id,))
    for item in favorites_data:
        cursor.execute("INSERT INTO favorite_items (user_id, flower_id) VALUES (?, ?)",
                       (user_id, item['id']))
    db.commit()


@app.route('/')
def home():
    is_admin = session.get('is_admin', False)
    user_logged_in = session.get('user_id') is not None

    search_query = request.args.get('search_query') # Get search query
    sort_order = request.args.get('sort')  # 'price_asc' or 'price_desc'
    flowers = load_products_from_db(search_query, sort_order) # Pass it to the loading function

    cart = []
    cart_count = 0
    favorites = []
    edit_mode = session.get('edit_mode', False)

    if user_logged_in:
        cart = session.get('cart', [])
        cart_count = sum(item['quantity'] for item in cart) if cart else 0
        favorites = session.get('favorites', [])
    else:
        session.pop('cart', None)
        session.pop('favorites', None)
        session.pop('edit_mode', None)

    return render_template('home.html', flowers=flowers, is_admin=is_admin,
                           cart_count=cart_count, favorites=favorites,
                           user_logged_in=user_logged_in, edit_mode=edit_mode,
                           search_query=search_query) # Pass search_query to template

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Route for user login."""
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        db = get_db_connection()
        user = db.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()

        if user and check_password_hash(user['password_hash'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['is_admin'] = (user['role'] == 'admin')

            # Load cart and favorites from DB into session after login
            session['cart'] = load_user_cart_from_db(user['id'])
            session['favorites'] = load_user_favorites_from_db(user['id'])

            session['edit_mode'] = False # Disable edit mode on login

        db = get_db_connection()
        user = db.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()

        if user and check_password_hash(user['password_hash'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['is_admin'] = (user['role'] == 'admin')

            # Load cart and favorites from DB into session after login
            session['cart'] = load_user_cart_from_db(user['id'])
            session['favorites'] = load_user_favorites_from_db(user['id'])

            session['edit_mode'] = False # Disable edit mode on login

            flash('Успішний вхід!', 'success')
            return redirect(url_for('home'))
        else:
            flash('Невірні логін або пароль.', 'danger')

    return render_template('admin_login.html')


@app.route('/logout')
def logout():
    """Route for user logout."""
    user_id = session.get('user_id')
    if user_id:
        # Save cart and favorites from session to DB before logout
        save_user_cart_to_db(user_id, session.get('cart', []))
        save_user_favorites_to_db(user_id, session.get('favorites', []))

    # Clear session
    session.pop('user_id', None)
    session.pop('username', None)
    session.pop('is_admin', None)
    session.pop('cart', None)       # Clear cart from session
    session.pop('favorites', None)  # Clear favorites from session
    session.pop('edit_mode', None)  # Disable edit mode
    flash('Ви вийшли з системи.', 'info')
    return redirect(url_for('home'))

@app.route('/toggle_edit_mode', methods=['POST'])
def toggle_edit_mode():
    """Toggles edit mode for administrators."""
    if not session.get('is_admin'):
        flash('Доступ заборонено. Тільки адміністратори можуть перемикати режим редагування.', 'danger')
        return redirect(url_for('login'))

    session['edit_mode'] = not session.get('edit_mode', False) # Toggle value
    flash(f"Режим редагування: {'увімкнено' if session['edit_mode'] else 'вимкнено'}.", 'info')
    return redirect(url_for('home'))


@app.route('/edit_flower/<int:flower_id>', methods=['POST'])
def edit_flower(flower_id):
    """
    Edits an existing product. Added ability to upload new image
    and delete old image.
    """
    if not session.get('is_admin') or not session.get('edit_mode'):
        flash('Доступ заборонено. Увімкніть режим редагування, щоб редагувати квіти.', 'danger')
        return redirect(url_for('home'))

    name = request.form['name']
    description = request.form['description']
    price = float(request.form['price'])
    image_file = request.files.get('image')

    db = get_db_connection()
    cursor = db.cursor()

    # Get the current product to retrieve the old image_url
    current_flower = get_flower_by_id(flower_id)
    old_image_url = current_flower['image_url'] if current_flower else None
    new_image_url = old_image_url # Default to old if no new image is uploaded

    if image_file and image_file.filename != '':
        if allowed_file(image_file.filename):
            try:
                original_filename = secure_filename(image_file.filename)
                file_ext = original_filename.rsplit('.', 1)[1].lower()
                unique_filename = f"{uuid.uuid4().hex}.{file_ext}"

                file_path = os.path.join(app.root_path, app.config['UPLOAD_FOLDER'], unique_filename)
                os.makedirs(os.path.dirname(file_path), exist_ok=True)
                image_file.save(file_path)

                new_image_url = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename).replace("\\", "/")
                flash(f"Нове зображення '{original_filename}' успішно завантажено.", "success")
                print(f"New image saved: {file_path}. URL for DB: {new_image_url}")

                # Delete the old image if it existed and is not one of the initial ones
                if old_image_url and "static/images/flower" not in old_image_url: # Skip initial images
                    old_file_path = os.path.join(app.root_path, old_image_url)
                    if os.path.exists(old_file_path):
                        try:
                            os.remove(old_file_path)
                            print(f"Old image deleted: {old_file_path}")
                        except OSError as e:
                            print(f"Error deleting old image {old_file_path}: {e}")
                            flash(f"Помилка при видаленні старого зображення: {e}", "warning")
            except Exception as e:
                flash(f"Помилка при завантаженні нового зображення: {e}", "danger")
                print(f"Image upload error: {e}")
                return redirect(url_for('home'))
        else:
            flash("Недопустимий формат файлу зображення для оновлення.", "danger")
            return redirect(url_for('home'))

    try:
        cursor.execute("UPDATE products SET name = ?, description = ?, price = ?, image_url = ? WHERE id = ?",
                       (name, description, price, new_image_url, flower_id))
        db.commit()
        flash(f"Товар \"{name}\" оновлено.", "success")
    except Exception as e:
        flash(f"Помилка при оновленні товару в базі даних: {e}", "danger")
        print(f"DB error updating product: {e}")
        db.rollback()

    return redirect(url_for('home'))


@app.route('/delete_flower/<int:flower_id>', methods=['POST'])
def delete_flower(flower_id):
    """
    Deletes a product from the database and its associated image.
    Only for administrators in edit mode.
    """
    if not session.get('is_admin') or not session.get('edit_mode'):
        flash('Доступ заборонено. Увімкніть режим редагування, щоб видаляти квіти.', 'danger')
        return redirect(url_for('home'))

    db = get_db_connection()
    cursor = db.cursor()

    flower = get_flower_by_id(flower_id)
    if not flower:
        flash("Товар не знайдено.", "danger")
        return redirect(url_for('home'))

    try:
        # Delete product from cart_items and favorite_items tables (via CASCADE)
        # and from the products table
        cursor.execute("DELETE FROM products WHERE id = ?", (flower_id,))
        db.commit()

        # Delete image if it exists and is not one of the initial ones
        if flower['image_url'] and "static/images/flower" not in flower['image_url']: # Skip initial images
            file_path = os.path.join(app.root_path, flower['image_url'])
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                    print(f"Image deleted: {file_path}")
                except OSError as e:
                    print(f"Error deleting image {file_path}: {e}")
                    flash(f"Помилка при видаленні зображення товару: {e}", "warning")

        flash(f"Товар \"{flower['name']}\" успішно видалено.", "success")
    except Exception as e:
        flash(f"Помилка при видаленні товару: {e}", "danger")
        print(f"DB error deleting product: {e}")
        db.rollback()

    return redirect(url_for('home'))


@app.route('/add_flower', methods=['POST'])
def add_flower():
    """
    Adds a new product (flower) to the database.
    Only for administrators in edit mode.
    """
    if not session.get('is_admin') or not session.get('edit_mode'):
        flash('Доступ заборонено. Увімкніть режим редагування, щоб додавати квіти.', 'danger')
        return redirect(url_for('home'))

    name = request.form.get('name')
    description = request.form.get('description')
    price = request.form.get('price')
    image_file = request.files.get('image')

    if not all([name, price]):
        flash("Будь ласка, заповніть назву та ціну товару.", "danger")
        return redirect(url_for('home'))

    try:
        price = float(price)
    except ValueError:
        flash("Ціна повинна бути числом.", "danger")
        return redirect(url_for('home'))

    image_url = None
    if image_file and image_file.filename != '':
        if allowed_file(image_file.filename):
            try:
                original_filename = secure_filename(image_file.filename)
                file_ext = original_filename.rsplit('.', 1)[1].lower()
                unique_filename = f"{uuid.uuid4().hex}.{file_ext}" # Use UUID for uniqueness

                # Full path to save the file
                file_path = os.path.join(app.root_path, app.config['UPLOAD_FOLDER'], unique_filename)

                # Check and create directory if it doesn't exist
                os.makedirs(os.path.dirname(file_path), exist_ok=True)

                image_file.save(file_path)

                # Save relative URL for use in Flask templates
                image_url = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename).replace("\\", "/")
                flash(f"Нове зображення '{original_filename}' успішно завантажено.", "success")
                print(f"New image saved: {file_path}. URL for DB: {image_url}") # Debugging print
            except Exception as e:
                flash(f"Помилка при збереженні зображення: {e}", "danger")
                print(f"Image save error: {e}") # Debugging print
                return redirect(url_for('home'))
        else:
            flash("Недопустимий формат файлу зображення.", "danger")
            return redirect(url_for('home'))
    else: # If no file selected or filename is empty
        flash("Товар буде додано без зображення.", "info")
        print("No image provided or file was empty.")


    db = get_db_connection()
    cursor = db.cursor()
    try:
        cursor.execute("INSERT INTO products (name, description, price, image_url) VALUES (?, ?, ?, ?)",
                       (name, description, price, image_url))
        db.commit()
        flash(f"Товар \"{name}\" успішно додано.", "success")
        print(f"Product '{name}' added to DB with URL: {image_url}") # Debugging print
    except Exception as e:
        flash(f"Помилка при додаванні товару до бази даних: {e}", "danger")
        print(f"DB error adding product: {e}") # Debugging print
        db.rollback()

    return redirect(url_for('home'))


@app.route('/add_to_cart/<int:flower_id>', methods=['POST'])
def add_to_cart(flower_id):
    """Adds an item to the user's cart."""
    user_id = session.get('user_id')
    if not user_id:
        flash('Будь ласка, увійдіть, щоб додати товари до кошика.', 'info')
        return redirect(url_for('login'))

    flower = get_flower_by_id(flower_id)
    if not flower:
        flash('Квітка не знайдена.', 'danger')
        return redirect(url_for('home'))

    # Get quantity from form. Default to 1 if not specified or invalid value.
    try:
        quantity = int(request.form.get('quantity', 1))
        if quantity < 1:
            quantity = 1 # Ensure quantity is not less than 1
    except ValueError:
        quantity = 1 # If conversion to number fails, set to 1

    db = get_db_connection()
    cursor = db.cursor()

    cursor.execute("SELECT quantity FROM cart_items WHERE user_id = ? AND flower_id = ?", (user_id, flower_id))
    existing_item_db = cursor.fetchone()

    if existing_item_db:
        new_quantity = existing_item_db['quantity'] + quantity
        cursor.execute("UPDATE cart_items SET quantity = ? WHERE user_id = ? AND flower_id = ?",
                       (new_quantity, user_id, flower_id))
        flash(f"{flower['name']}: кількість збільшено до {new_quantity}.", "success")
    else:
        cursor.execute("INSERT INTO cart_items (user_id, flower_id, quantity) VALUES (?, ?, ?)",
                       (user_id, flower_id, quantity))
        flash(f"{flower['name']} (x{quantity}) додано до кошика.", "success")
    db.commit()

    # Update cart in session from DB
    session['cart'] = load_user_cart_from_db(user_id)
    return redirect(url_for('home'))

@app.route('/remove_from_cart/<int:index>', methods=['POST'])
def remove_from_cart(index):
    """Removes an item from the cart by index."""
    user_id = session.get('user_id')
    if not user_id:
        flash('Будь ласка, увійдіть.', 'info')
        return redirect(url_for('login'))

    cart = session.get('cart', [])
    if 0 <= index < len(cart):
        removed_item = cart[index]

        db = get_db_connection()
        cursor = db.cursor()
        cursor.execute("DELETE FROM cart_items WHERE user_id = ? AND flower_id = ?",
                       (user_id, removed_item['id']))
        db.commit()

        # Update cart in session from DB
        session['cart'] = load_user_cart_from_db(user_id)
        flash(f"{removed_item['name']} видалено з кошика.", "info")
    else:
        flash("Товар не знайдено в кошику.", "danger")
    return redirect(url_for('view_cart'))

@app.route('/increase_quantity/<int:index>', methods=['POST'])
def increase_quantity(index):
    """Increases the quantity of an item in the cart by index."""
    user_id = session.get('user_id')
    if not user_id:
        flash('Будь ласка, увійдіть.', 'info')
        return redirect(url_for('login'))

    cart = session.get('cart', [])
    if 0 <= index < len(cart):
        item_to_update = cart[index]
        db = get_db_connection()
        cursor = db.cursor()

        cursor.execute("UPDATE cart_items SET quantity = quantity + 1 WHERE user_id = ? AND flower_id = ?",
                       (user_id, item_to_update['id']))
        db.commit()

        # Update cart in session from DB
        session['cart'] = load_user_cart_from_db(user_id)
    return redirect(url_for('view_cart'))

@app.route('/decrease_quantity/<int:index>', methods=['POST'])
def decrease_quantity(index):
    """Decreases the quantity of an item in the cart by index."""
    user_id = session.get('user_id')
    if not user_id:
        flash('Будь ласка, увійдіть.', 'info')
        return redirect(url_for('login'))

    cart = session.get('cart', [])
    if 0 <= index < len(cart):
        item_to_update = cart[index]
        db = get_db_connection()
        cursor = db.cursor()

        cursor.execute("SELECT quantity FROM cart_items WHERE user_id = ? AND flower_id = ?",
                       (user_id, item_to_update['id']))
        current_quantity = cursor.fetchone()['quantity']

        if current_quantity > 1:
            cursor.execute("UPDATE cart_items SET quantity = quantity - 1 WHERE user_id = ? AND flower_id = ?",
                           (user_id, item_to_update['id']))
            db.commit()

        # Update cart in session from DB
        session['cart'] = load_user_cart_from_db(user_id)
    return redirect(url_for('view_cart'))

@app.route('/cart')
def view_cart():
    """Visualise items in user's cart"""
    if not session.get('user_id'):
        flash('Будь ласка, увійдіть, щоб переглянути ваш кошик.', 'info')
        return redirect(url_for('login'))

    cart = session.get('cart', [])
    total = sum(item['price'] * item['quantity'] for item in cart)

    exchange_rate = get_uah_to_eur_rate()
    approx_total_eur = round(total / exchange_rate, 2) if exchange_rate else 0

    user_logged_in = session.get('user_id') is not None
    cart_count = sum(item['quantity'] for item in session.get('cart', [])) if user_logged_in else 0
    favorites = session.get('favorites', []) if user_logged_in else []

    return render_template('cart.html',
                           cart=cart,
                           total=total,
                           cart_count=cart_count,
                           favorites=favorites,
                           user_logged_in=user_logged_in,
                           exchange_rate=exchange_rate,
                           approx_total_eur=approx_total_eur)

@app.route('/checkout', methods=['GET', 'POST'])
def checkout():
    """Route for placing an order."""
    user_id = session.get('user_id')
    if not user_id:
        flash('Будь ласка, увійдіть, щоб оформити замовлення.', 'info')
        return redirect(url_for('login'))

    # Pass cart_count and favorites for display in the top bar
    user_logged_in = session.get('user_id') is not None
    cart_count = sum(item['quantity'] for item in session.get('cart', [])) if user_logged_in else 0
    favorites = session.get('favorites', []) if user_logged_in else []

    return render_template('checkout.html',
                           publishable_key=app.config['STRIPE_PUBLISHABLE_KEY'],
                           cart_count=cart_count, favorites=favorites,
                           user_logged_in=user_logged_in)


@app.route('/create-checkout-session', methods=['POST'])
def create_checkout_session():
    user_id = session.get('user_id')
    if not user_id:
        flash('Будь ласка, увійдіть, щоб оформити замовлення.', 'info')
        return redirect(url_for('login'))

    cart = session.get('cart', [])
    if not cart:
        flash('Ваш кошик порожній.', 'info')
        return redirect(url_for('view_cart'))

    exchange_rate = get_uah_to_eur_rate()
    line_items = []

    for item in cart:
        price_uah = item['price']
        price_eur = round(price_uah / exchange_rate, 2)
        line_items.append({
            'price_data': {
                'currency': 'eur',
                'product_data': {'name': item['name']},
                'unit_amount': int(price_eur * 100),  # rate uah to eur
            },
            'quantity': item['quantity'],
        })

    checkout_session = stripe.checkout.Session.create(
        payment_method_types=['card'],
        line_items=line_items,
        mode='payment',
        success_url=url_for('checkout_success', _external=True) + '?session_id={CHECKOUT_SESSION_ID}',
        cancel_url=url_for('checkout_cancel', _external=True),
    )

    return jsonify({'sessionId': checkout_session.id})


@app.route('/checkout/success')
def checkout_success():
    """Stripe payment success route."""
    user_id = session.get('user_id')
    db = get_db_connection()
    db.execute("DELETE FROM cart_items WHERE user_id = ?", (user_id,))
    db.commit()
    session.pop('cart', None)
    flash("Оплата успішна! Дякуємо за замовлення.", "success")
    return redirect(url_for('home'))

@app.route('/checkout/cancel')
def checkout_cancel():
    """Stripe payment cancellation route."""
    flash("Оплата скасована, ви повернулися до кошика.", "warning")
    return redirect(url_for('view_cart'))


@app.route('/register', methods=['GET', 'POST'])
def register():
    """Route for new user registration."""
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        confirm = request.form.get('confirm')

        if not all([username, password, confirm]): # Check that all fields are filled
            flash("Будь ласка, заповніть усі поля.", "danger")
        elif password != confirm:
            flash("Паролі не збігаються.", "danger")
        else:
            db = get_db_connection()
            try:
                hashed_password = generate_password_hash(password)
                cursor = db.cursor()
                cursor.execute("INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                               (username, hashed_password, 'user'))
                db.commit()
                flash("Реєстрація успішна! Тепер увійдіть.", "success")
                return redirect(url_for('login'))
            except sqlite3.IntegrityError: # Handle error if user already exists
                flash("Користувач з таким ім'ям вже існує.", "danger")
            except Exception as e:
                flash(f"Помилка реєстрації: {e}", "danger")
                db.rollback()

    return render_template('register.html')

@app.route('/favorites')
def view_favorites():
    """Route for viewing favorite items."""
    if not session.get('user_id'):
        flash('Будь ласка, увійдіть, щоб переглянути ваші улюблені товари.', 'info')
        return redirect(url_for('login'))

    favorites = session.get('favorites', []) # Get favorites from session

    # Pass cart_count and favorites for display in the top bar
    user_logged_in = session.get('user_id') is not None
    cart_count = sum(item['quantity'] for item in session.get('cart', [])) if user_logged_in else 0
    # The 'favorites' variable is already defined and passed correctly. Remove duplicate.

    return render_template('favorites.html', favorites=favorites,
                           cart_count=cart_count, # Removed duplicate 'favorites=favorites' here
                           user_logged_in=user_logged_in)

@app.route('/add_to_favorites/<int:flower_id>', methods=['POST'])
def add_to_favorites(flower_id):
    """Adds an item to the favorites list."""
    user_id = session.get('user_id')
    if not user_id:
        flash('Будь ласка, увійдіть, щоб додати товари до обраного.', 'info')
        return redirect(url_for('login'))

    flower = get_flower_by_id(flower_id)
    if not flower:
        flash('Квітка не знайдена.', 'danger')
        return redirect(url_for('home'))

    db = get_db_connection()
    cursor = db.cursor()

    try:
        cursor.execute("INSERT INTO favorite_items (user_id, flower_id) VALUES (?, ?)",
                       (user_id, flower_id))
        db.commit()
        # Update favorites in session from DB
        session['favorites'] = load_user_favorites_from_db(user_id)
        flash(f"{flower['name']} додано в обране.", "success")
    except sqlite3.IntegrityError: # Handle if item is already in favorites
        flash("Ця квітка вже в обраному.", "info")
        db.rollback()
    except Exception as e:
        flash(f"Помилка додавання до обраного: {e}", "danger")
        db.rollback()

    return redirect(url_for('home'))

@app.route('/remove_from_favorites/<int:flower_id>', methods=['POST'])
def remove_from_favorites(flower_id):
    """Removes an item from the favorites list."""
    user_id = session.get('user_id')
    if not user_id:
        flash('Будь ласка, увійдіть.', 'info')
        return redirect(url_for('login'))

    db = get_db_connection()
    cursor = db.cursor()

    flower_name_cursor = db.execute("SELECT name FROM products WHERE id = ?", (flower_id,)).fetchone()
    flower_name = flower_name_cursor['name'] if flower_name_cursor else "Unknown product (possibly deleted)"

    try:
        cursor.execute("DELETE FROM favorite_items WHERE user_id = ? AND flower_id = ?",
                       (user_id, flower_id))
        db.commit()
        flash(f"Товар \"{flower_name}\" видалено з обраного.", "info")
    except Exception as e:
        flash(f"Помилка при видаленні з обраного: {e}", "danger")
        print(f"Error removing from favorites: {e}")
        db.rollback()

    # Update favorites in session from DB
    session['favorites'] = load_user_favorites_from_db(user_id)
    return redirect(url_for('view_favorites'))

@app.route('/profile')
def profile():
    """Route for viewing user profile and changing password."""
    if not session.get('user_id'):
        flash('Будь ласка, увійдіть, щоб переглянути ваш профіль.', 'info')
        return redirect(url_for('login'))

    username = session.get('username')

    # Load cart and favorites from session for the top bar icons
    user_logged_in = session.get('user_id') is not None
    cart_count = sum(item['quantity'] for item in session.get('cart', [])) if user_logged_in else 0
    favorites = session.get('favorites', []) if user_logged_in else []

    return render_template('profile.html',
                           username=username,
                           cart_count=cart_count, # Passed to template
                           favorites=favorites,    # Passed to template
                           user_logged_in=user_logged_in) # Also passed for consistency

@app.route('/update_password', methods=['POST'])
def update_password():
    """Route for updating user password."""
    user_id = session.get('user_id')
    if not user_id:
        flash('Будь ласка, увійдіть, щоб змінити пароль.', 'info')
        return redirect(url_for('login'))

    old_password = request.form.get('old_password')
    new_password = request.form.get('new_password')
    confirm_new_password = request.form.get('confirm_new_password')

    if not all([old_password, new_password, confirm_new_password]):
        flash("Будь ласка, заповніть усі поля.", "danger")
        return redirect(url_for('profile'))

    if new_password != confirm_new_password:
        flash("Новий пароль та підтвердження не збігаються.", "danger")
        return redirect(url_for('profile'))

    if len(new_password) < 6:
        flash("Новий пароль має бути не менше 6 символів.", "danger")
        return redirect(url_for('profile'))

    db = get_db_connection()
    user = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()

    if user and check_password_hash(user['password_hash'], old_password):
        hashed_new_password = generate_password_hash(new_password)
        db.execute("UPDATE users SET password_hash = ? WHERE id = ?",
                   (hashed_new_password, user_id))
        db.commit()
        flash("Пароль успішно оновлено!", "success")
        return redirect(url_for('profile'))
    else:
        flash("Невірний старий пароль.", "danger")
        return redirect(url_for('profile'))

@app.template_filter('date')
def format_date(value, format="%Y"):
    """
    Formats a datetime object or "now" string to the specified format.
    Accepts "now" to get the current date.
    """
    if value == 'now':
        return datetime.datetime.now().strftime(format)
    elif isinstance(value, datetime.datetime):
        return value.strftime(format)
    try:
        dt_object = datetime.datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
        return dt_object.strftime(format)
    except (TypeError, ValueError):
        return value

# Route for viewing product details and reviews
@app.route('/product/<int:product_id>')
def product_detail(product_id):
    """Route for displaying the product details page with reviews."""
    user_logged_in = session.get('user_id') is not None
    flower = get_flower_by_id(product_id)
    if not flower:
        flash('Товар не знайдено.', 'danger')
        return redirect(url_for('home'))

    reviews = get_reviews_for_product(product_id)
    average_rating = get_average_rating_for_product(product_id)

    # Check if the current user has already left a review
    user_has_reviewed = False
    if user_logged_in:
        db = get_db_connection()
        cursor = db.execute("SELECT COUNT(*) FROM reviews WHERE user_id = ? AND product_id = ?",
                           (session.get('user_id'), product_id))
        if cursor.fetchone()[0] > 0:
            user_has_reviewed = True

    cart_count = sum(item['quantity'] for item in session.get('cart', [])) if user_logged_in else 0
    favorites = session.get('favorites', []) if user_logged_in else []

    return render_template('product_detail.html',
                           flower=flower,
                           reviews=reviews,
                           average_rating=average_rating,
                           user_logged_in=user_logged_in,
                           cart_count=cart_count,
                           favorites=favorites,
                           user_has_reviewed=user_has_reviewed)

# Route for adding a review
@app.route('/product/<int:product_id>/add_review', methods=['POST'])
def add_review(product_id):
    """Route for adding a new review to a product."""
    user_id = session.get('user_id')
    if not user_id:
        flash('Будь ласка, увійдіть, щоб залишити відгук.', 'info')
        return redirect(url_for('login'))

    rating = request.form.get('rating')
    comment = request.form.get('comment')

    # Check if the user has already left a review
    db = get_db_connection()
    cursor = db.execute("SELECT COUNT(*) FROM reviews WHERE user_id = ? AND product_id = ?",
                       (user_id, product_id))
    if cursor.fetchone()[0] > 0:
        flash('Ви вже залишили відгук для цього товару.', 'warning')
        return redirect(url_for('product_detail', product_id=product_id))


    if not rating:
        flash('Будь ласка, оберіть оцінку.', 'danger')
        return redirect(url_for('product_detail', product_id=product_id))

    try:
        rating = int(rating)
        if not (1 <= rating <= 5):
            raise ValueError("Rating must be between 1 and 5.")
    except ValueError:
        flash('Оцінка повинна бути числом від 1 до 5.', "danger")
        return redirect(url_for('product_detail', product_id=product_id))

    if not comment:
        comment = "" # Allow empty comments, but it's better to encourage them

    try:
        cursor = db.cursor()
        cursor.execute(
            "INSERT INTO reviews (product_id, user_id, rating, comment) VALUES (?, ?, ?, ?)",
            (product_id, user_id, rating, comment)
        )
        db.commit()
        flash('Ваш відгук успішно додано!', 'success')
    except Exception as e:
        flash(f"Помилка при додаванні відгуку: {e}", "danger")
        db.rollback()

    return redirect(url_for('product_detail', product_id=product_id))


if __name__ == '__main__':
    app.run(debug=True)
