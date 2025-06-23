from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, g
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
import datetime
import os
import stripe
from app.utils import allowed_file, get_uah_to_eur_rate
from app.db import init_db, get_db_connection
from app.config import Config
from dotenv import load_dotenv, find_dotenv
from werkzeug.utils import secure_filename
import uuid # Import uuid for generating unique filenames and reset tokens

load_dotenv(find_dotenv())


app = Flask(__name__)
app.config.from_object(Config)
stripe.api_key = app.config['STRIPE_SECRET_KEY']


with app.app_context():
    init_db()


def load_products_from_db(search_term=None, sort_order=None):
    """
    Loads all products (flowers) from the products table.
    Filters products by name or description if search_term is provided (case-insensitive for all characters).
    Sorts products based on sort_order ('price_asc', 'price_desc', 'newest', 'oldest', 'name_asc', 'name_desc').
    Default sort is 'name_asc'.
    """
    db = get_db_connection()
    cursor = db.cursor()

    # Fetch all products first
    # Selects all columns including 'stock'
    cursor.execute("SELECT * FROM products")
    all_products = cursor.fetchall() # Get all rows as a list of sqlite3.Row objects

    filtered_products = []
    if search_term:
        search_term_lower = search_term.lower() # Convert search term to lowercase once

        for product in all_products:
            # Convert product name and description to lowercase in Python for robust comparison
            name_lower = product['name'].lower() if product['name'] else ''
            description_lower = product['description'].lower() if product['description'] else ''

            if search_term_lower in name_lower or search_term_lower in description_lower:
                filtered_products.append(product)
        products_to_sort = filtered_products
    else:
        products_to_sort = list(all_products) # Convert to list as all_products is a cursor result

    # Apply sorting logic in Python
    if sort_order == 'price_asc':
        products_to_sort.sort(key=lambda p: p['price'])
    elif sort_order == 'price_desc':
        products_to_sort.sort(key=lambda p: p['price'], reverse=True)
    elif sort_order == 'newest': # Sort by newest (highest ID first)
        products_to_sort.sort(key=lambda p: p['id'], reverse=True)
    elif sort_order == 'oldest': # Sort by oldest (lowest ID first)
        products_to_sort.sort(key=lambda p: p['id'])
    elif sort_order == 'name_asc': # Sort by name A-Z
        products_to_sort.sort(key=lambda p: p['name'].lower())
    elif sort_order == 'name_desc': # Sort by name Z-A
        products_to_sort.sort(key=lambda p: p['name'].lower(), reverse=True)
    else:
        # Default sort to 'name_asc' if no specific sort_order is provided or recognized
        products_to_sort.sort(key=lambda p: p['name'].lower())

    return products_to_sort


@app.route('/get_flower_data/<int:flower_id>', methods=['GET'])
def get_flower_data(flower_id):
    """
    Returns data for a single flower as JSON.
    Used by AJAX to populate the edit modal.
    """
    flower = get_flower_by_id(flower_id)
    if flower:
        # Convert sqlite3.Row object to a dictionary for JSON serialization
        flower_dict = dict(flower)
        # Ensure image_url is a full path if it's relative
        if flower_dict.get('image_url') and not flower_dict['image_url'].startswith(('http://', 'https://', '/static')):
            # Ensure the correct base path for static files.
            # Assuming flower_dict['image_url'] is like 'static/images/flower.jpg'
            # We want it to be '/static/images/flower.jpg' for correct URL generation.
            if flower_dict['image_url'].startswith('static/'):
                 flower_dict['image_url'] = '/' + flower_dict['image_url']
            else:
                 # Fallback for other unexpected relative paths, prepend /static/images/ if it's just a filename
                 flower_dict['image_url'] = f'/static/images/{flower_dict["image_url"]}'

        return jsonify(flower_dict)
    return jsonify({'error': 'Flower not found'}), 404


def get_reviews_for_product(product_id):
    """
    Returns all reviews for a specific product, ordered by creation date (newest first).
    Converts timestamps from UTC (as stored by SQLite) to Kyiv time (UTC+3).
    """
    db = get_db_connection()
    cursor = db.execute("""
        SELECT r.id, r.rating, r.comment, r.created_at, u.username, r.user_id
        FROM reviews r
        JOIN users u ON r.user_id = u.id
        WHERE r.product_id = ?
        ORDER BY r.created_at DESC
    """, (product_id,))

    reviews_data = []
    kyiv_offset = datetime.timedelta(hours=3) # Kyiv time is UTC+3 (EEST/EET without considering DST specifics)

    for row in cursor.fetchall():
        # Parse UTC time string from DB
        try:
            utc_dt = datetime.datetime.strptime(row['created_at'], "%Y-%m-%d %H:%M:%S")
            # Convert to Kyiv time by adding the offset
            kyiv_dt = utc_dt + kyiv_offset
            formatted_time = kyiv_dt.strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            # Fallback if timestamp format is unexpected
            formatted_time = row['created_at']

        item = {
            'id': row['id'],
            'rating': row['rating'],
            'comment': row['comment'],
            'created_at': formatted_time,
            'username': row['username'],
            'user_id': row['user_id']
        }
        reviews_data.append(item)
    return reviews_data


def get_flower_by_id(flower_id):
    """Returns a flower object by ID from the database."""
    db = get_db_connection()
    # Selects all columns including 'stock'
    cursor = db.execute("SELECT * FROM products WHERE id = ?", (flower_id,))
    return cursor.fetchone()


def get_average_rating_for_product(product_id):
    """Calculates the average rating for a specific product."""
    db = get_db_connection()
    cursor = db.execute("SELECT AVG(rating) FROM reviews WHERE product_id = ?", (product_id,))
    avg_rating = cursor.fetchone()[0]
    return round(avg_rating, 2) if avg_rating else 0.0


def load_user_cart_from_db(user_id):
    """Loads user's cart items from the database."""
    db = get_db_connection()
    # Ensure 'stock' is also fetched for cart items if needed for display later or validation.
    # For now, it's implicitly included by SELECT p.*
    cursor = db.execute("""
        SELECT ci.quantity, p.id, p.name, p.description, p.price, p.image_url, p.stock
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
            'quantity': row['quantity'],
            'stock': row['stock'] # Include stock in cart item data
        }
        cart_data.append(item)
    return cart_data

def save_user_cart_to_db(user_id, cart_data):
    """Saves user's cart items from the session to the database."""
    db = get_db_connection()
    cursor = db.cursor()
    cursor.execute("DELETE FROM cart_items WHERE user_id = ?", (user_id,)) # Clear existing cart
    for item in cart_data:
        cursor.execute("INSERT INTO cart_items (user_id, flower_id, quantity) VALUES (?, ?, ?)",
                       (user_id, item['id'], item['quantity']))
    db.commit()

def load_user_favorites_from_db(user_id):
    """Loads user's favorite items from the database."""
    db = get_db_connection()
    cursor = db.execute("""
        SELECT p.id, p.name, p.description, p.price, p.image_url, p.stock
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
            'stock': row['stock'] # Include stock in favorite item data
        }
        favorites_data.append(item)
    return favorites_data

def save_user_favorites_to_db(user_id, favorites_data):
    """Saves user's favorite items from the session to the database."""
    db = get_db_connection()
    cursor = db.cursor()
    cursor.execute("DELETE FROM favorite_items WHERE user_id = ?", (user_id,)) # Clear existing favorites
    for item in favorites_data:
        cursor.execute("INSERT INTO favorite_items (user_id, flower_id) VALUES (?, ?)",
                       (user_id, item['id']))
    db.commit()


@app.route('/')
def home():
    """
    Handles the home page, displaying products with search and sort functionality.
    Manages user session, cart, and favorites data for display.
    """
    is_admin = session.get('is_admin', False)
    user_logged_in = session.get('user_id') is not None

    search_query = request.args.get('search_query') # Get search query from URL parameters
    # Set default sort_order to 'name_asc' if not provided in the URL
    sort_order = request.args.get('sort', 'name_asc')  # Default to 'name_asc'
    flowers = load_products_from_db(search_query, sort_order) # Load products based on search and sort

    cart = []
    cart_count = 0
    favorites = []
    edit_mode = session.get('edit_mode', False)

    if user_logged_in:
        # Load cart and favorites from session (which are kept in sync with DB)
        cart = session.get('cart', [])
        cart_count = sum(item['quantity'] for item in cart) if cart else 0
        favorites = session.get('favorites', [])
    else:
        # Clear session-related data if user is not logged in
        session.pop('cart', None)
        session.pop('favorites', None)
        session.pop('edit_mode', None)

    return render_template('home.html', flowers=flowers, is_admin=is_admin,
                           cart_count=cart_count, favorites=favorites,
                           user_logged_in=user_logged_in, edit_mode=edit_mode,
                           search_query=search_query, sort_order=sort_order) # Pass search_query and sort_order to template

@app.route('/login', methods=['GET', 'POST'])
def login():
    """
    Handles user login. Authenticates user and sets session variables.
    Loads user's cart and favorites from DB into session upon successful login.
    """
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

            session['edit_mode'] = False # Disable edit mode on login by default

            flash('Успішний вхід!', 'success')
            return redirect(url_for('home'))
        else:
            flash('Невірні логін або пароль.', 'danger')

    user_logged_in = session.get('user_id') is not None
    cart_count = sum(item['quantity'] for item in session.get('cart', [])) if user_logged_in else 0
    favorites = session.get('favorites', []) if user_logged_in else []
    is_admin = session.get('is_admin', False)

    return render_template('admin_login.html',
                           cart_count=cart_count,
                           favorites=favorites,
                           user_logged_in=user_logged_in,
                           is_admin=is_admin)

@app.route('/logout')
def logout():
    """
    Handles user logout. Saves user's cart and favorites from session to DB,
    then clears all relevant session variables.
    """
    user_id = session.get('user_id')
    if user_id:
        # Save cart and favorites from session to DB before logout
        save_user_cart_to_db(user_id, session.get('cart', []))
        save_user_favorites_to_db(user_id, session.get('favorites', []))

    # Clear session variables
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
    """
    Toggles edit mode for administrators.
    Only accessible by logged-in administrators.
    """
    if not session.get('is_admin'):
        flash('Доступ заборонено. Тільки адміністратори можуть перемикати режим редагування.', 'danger')
        return redirect(url_for('login'))

    session['edit_mode'] = not session.get('edit_mode', False) # Toggle the edit_mode boolean
    flash(f"Режим редагування: {'увімкнено' if session['edit_mode'] else 'вимкнено'}.", 'info')
    return redirect(url_for('home'))


@app.route('/edit_flower/<int:flower_id>', methods=['POST'])
def edit_flower(flower_id):
    """
    Edits an existing product in the database.
    Allows updating name, description, price, image, and stock.
    Handles deletion of old images if a new one is uploaded (except initial default images).
    Requires administrator privileges and edit mode to be active.
    """
    if not session.get('is_admin') or not session.get('edit_mode'):
        flash('Доступ заборонено. Увімкніть режим редагування, щоб редагувати квіти.', 'danger')
        return redirect(url_for('home'))

    name = request.form['name']
    description = request.form['description']
    image_file = request.files.get('image')

    # Price validation
    try:
        price = float(request.form['price'])
        if price < 0:
            flash("Ціна товару не може бути від'ємною.", "danger")
            return redirect(url_for('home'))
    except ValueError:
        flash("Ціна товару повинна бути числом.", "danger")
        return redirect(url_for('home'))

    # Stock validation
    try:
        stock = int(request.form['stock'])
        if stock < 0:
            flash("Кількість товару в наявності не може бути від'ємною.", "danger")
            return redirect(url_for('home'))
    except ValueError:
        flash("Кількість товару в наявності повинна бути цілим числом.", "danger")
        return redirect(url_for('home'))


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
                unique_filename = f"{uuid.uuid4().hex}.{file_ext}" # Generate unique filename

                file_path = os.path.join(app.root_path, app.config['UPLOAD_FOLDER'], unique_filename)
                os.makedirs(os.path.dirname(file_path), exist_ok=True) # Ensure directory exists
                image_file.save(file_path)

                new_image_url = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename).replace("\\", "/")
                flash(f"Нове зображення '{original_filename}' успішно завантажено.", "success")
                print(f"New image saved: {file_path}. URL for DB: {new_image_url}")

                # Delete the old image if it existed and is not one of the initial default images
                if old_image_url and "static/images/flower" not in old_image_url:
                    old_file_path = os.path.join(app.root_path, old_image_url)
                    if os.path.exists(old_file_path):
                        try:
                            os.remove(old_file_path)
                            print(f"Old image deleted: {old_file_path}")
                        except OSError as e:
                            print(f"Error deleting old image {file_path}: {e}")
                            flash(f"Помилка при видаленні старого зображення: {e}", "warning")
            except Exception as e:
                flash(f"Помилка при завантаженні нового зображення: {e}", "danger")
                print(f"Image upload error: {e}")
                return redirect(url_for('home'))
        else:
            flash("Недопустимий формат файлу зображення для оновлення.", "danger")
            return redirect(url_for('home'))

    try:
        # Update query to include stock
        cursor.execute("UPDATE products SET name = ?, description = ?, price = ?, image_url = ?, stock = ? WHERE id = ?",
                       (name, description, price, new_image_url, stock, flower_id))
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
    Deletes a product from the database and its associated image file.
    Requires administrator privileges and edit mode to be active.
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
        # Deleting the product will automatically delete related cart_items and favorite_items due to CASCADE
        cursor.execute("DELETE FROM products WHERE id = ?", (flower_id,))
        db.commit()

        # Delete image file if it exists and is not one of the initial default images
        if flower['image_url'] and "static/images/flower" not in flower['image_url']:
            file_path = os.path.join(app.root_path, flower['image_url'])
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                    print(f"Image deleted: {file_path}")
                except OSError as e:
                    print(f"Error deleting image {file_path}: {e}")
                    flash(f"Помилка при видаленні старого зображення: {e}", "warning")

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
    Allows uploading an image for the new product and setting initial stock.
    Requires administrator privileges and edit mode to be active.
    """
    if not session.get('is_admin') or not session.get('edit_mode'):
        flash('Доступ заборонено. Увімкніть режим редагування, щоб додавати квіти.', 'danger')
        return redirect(url_for('home'))

    name = request.form.get('name')
    description = request.form.get('description')
    price_str = request.form.get('price') # Get as string first
    stock_str = request.form.get('stock') # Get as string first
    image_file = request.files.get('image')

    if not all([name, price_str, stock_str]): # Ensure all basic fields are filled
        flash("Будь ласка, заповніть усі поля: назву, ціну та кількість в наявності.", "danger")
        return redirect(url_for('home'))

    try:
        price = float(price_str)
        if price < 0:
            flash("Ціна товару не може бути від'ємною.", "danger")
            return redirect(url_for('home'))
        stock = int(stock_str)
        if stock < 0:
            flash("Кількість товару в наявності не може бути від'ємною.", "danger")
            return redirect(url_for('home'))
    except ValueError:
        flash("Ціна повинна бути числом, а кількість в наявності - цілим числом.", "danger")
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
                print(f"New image saved: {file_path}. URL for DB: {image_url}")
            except Exception as e:
                flash(f"Помилка при збереженні зображення: {e}", "danger")
                print(f"Image save error: {e}")
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
        # Insert query now includes stock
        cursor.execute("INSERT INTO products (name, description, price, image_url, stock) VALUES (?, ?, ?, ?, ?)",
                       (name, description, price, image_url, stock))
        db.commit()
        flash(f"Товар \"{name}\" успішно додано.", "success")
        print(f"Product '{name}' added to DB with URL: {image_url}, Stock: {stock}")
    except Exception as e:
        flash(f"Помилка при додаванні товару до бази даних: {e}", "danger")
        print(f"DB error adding product: {e}")
        db.rollback()

    return redirect(url_for('home'))


@app.route('/add_to_cart/<int:flower_id>', methods=['POST'])
def add_to_cart(flower_id):
    """
    Adds a specified quantity of an item to the user's cart.
    If the item already exists, increases its quantity.
    Includes stock validation.
    Requires user to be logged in.
    """
    user_id = session.get('user_id')
    if not user_id:
        flash('Будь ласка, увійдіть, щоб додати товари до кошика.', 'info')
        return redirect(url_for('login'))

    flower = get_flower_by_id(flower_id)
    if not flower:
        flash('Квітка не знайдена.', 'danger')
        return redirect(url_for('home'))

    # Get quantity from form. Default to 1 if not specified or invalid.
    try:
        quantity = int(request.form.get('quantity', 1))
        if quantity < 1:
            quantity = 1 # Ensure quantity is not less than 1
    except ValueError:
        quantity = 1 # If conversion to number fails, set to 1

    # Stock Validation
    if flower['stock'] == 0:
        flash(f"На жаль, '{flower['name']}' наразі відсутня на складі.", "danger")
        return redirect(url_for('product_detail', product_id=flower_id))

    if quantity > flower['stock']:
        flash(f"На жаль, ви не можете додати {quantity} од. '{flower['name']}'. В наявності лише {flower['stock']} од.", "warning")
        return redirect(url_for('product_detail', product_id=flower_id))


    db = get_db_connection()
    cursor = db.cursor()

    # Check if the item already exists in the cart for this user
    cursor.execute("SELECT quantity FROM cart_items WHERE user_id = ? AND flower_id = ?", (user_id, flower_id))
    existing_item_db = cursor.fetchone()

    if existing_item_db:
        new_quantity = existing_item_db['quantity'] + quantity
        # Additional check to prevent exceeding stock when updating quantity
        if new_quantity > flower['stock']:
            flash(f"Не вдалося оновити кількість '{flower['name']}'. Загальна кількість в кошику ({new_quantity}) перевищує наявний запас ({flower['stock']}).", "warning")
            return redirect(url_for('product_detail', product_id=flower_id))

        cursor.execute("UPDATE cart_items SET quantity = ? WHERE user_id = ? AND flower_id = ?",
                       (new_quantity, user_id, flower_id))
        flash(f"{flower['name']}: кількість збільшено до {new_quantity}.", "success")
    else:
        cursor.execute("INSERT INTO cart_items (user_id, flower_id, quantity) VALUES (?, ?, ?)",
                       (user_id, flower_id, quantity))
        flash(f"{flower['name']} (x{quantity}) додано до кошика.", "success")
    db.commit()

    # Update cart in session by re-loading from DB to ensure consistency
    session['cart'] = load_user_cart_from_db(user_id)
    return redirect(url_for('home', product_id=flower_id))


@app.route('/update_cart_item_quantity/<int:flower_id>', methods=['POST'])
def update_cart_item_quantity(flower_id):
    """
    Updates the quantity of a specific item in the user's cart.
    If quantity is 0 or less, the item is removed.
    Includes stock validation.
    Requires user to be logged in.
    """
    user_id = session.get('user_id')
    if not user_id:
        flash('Будь ласка, увійдіть, щоб оновити кошик.', 'info')
        return redirect(url_for('login'))

    try:
        new_quantity = int(request.form.get('quantity', 1))
    except ValueError:
        flash('Недійсна кількість.', 'danger')
        return redirect(url_for('view_cart'))

    db = get_db_connection()
    cursor = db.cursor()

    flower = get_flower_by_id(flower_id)
    if not flower:
        flash('Квітка не знайдена.', 'danger')
        return redirect(url_for('view_cart'))

    if new_quantity <= 0:
        cursor.execute("DELETE FROM cart_items WHERE user_id = ? AND flower_id = ?",
                       (user_id, flower_id))
        flash(f"Товар '{flower['name']}' видалено з кошика.", "info") # Додано назву товару
    else:
        #Stock Validation for update
        if new_quantity > flower['stock']:
            flash(f"Не вдалося оновити кількість '{flower['name']}'. Загальна кількість в кошику ({new_quantity}) перевищує наявний запас ({flower['stock']}).", "warning")
            return redirect(url_for('view_cart'))


        cursor.execute("SELECT * FROM cart_items WHERE user_id = ? AND flower_id = ?", (user_id, flower_id))
        existing_item = cursor.fetchone()
        if existing_item:
            cursor.execute("UPDATE cart_items SET quantity = ? WHERE user_id = ? AND flower_id = ?",
                           (new_quantity, user_id, flower_id))
            flash(f"Кількість товару '{flower['name']}' оновлено до {new_quantity}.", "success") # Додано назву товару
        else:
            flash("Товар не знайдено в кошику для оновлення.", "danger")
    db.commit()

    # Update cart in session by re-loading from DB to ensure consistency
    session['cart'] = load_user_cart_from_db(user_id)
    return redirect(url_for('view_cart'))


@app.route('/remove_from_cart/<int:index>', methods=['POST'])
def remove_from_cart(index):
    """
    Removes an item from the user's cart based on its index in the session cart list.
    Requires user to be logged in.
    """
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

        # Update cart in session by re-loading from DB to ensure consistency
        session['cart'] = load_user_cart_from_db(user_id)
        flash(f"{removed_item['name']} видалено з кошика.", "info")
    else:
        flash("Товар не знайдено в кошику.", "danger")
    return redirect(url_for('view_cart'))


@app.route('/cart')
def view_cart():
    """
    Displays the user's shopping cart, calculating total price
    and approximate total in EUR using the current exchange rate.
    Requires user to be logged in.
    """
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
    is_admin = session.get('is_admin', False) # Передача is_admin

    return render_template('cart.html',
                           cart=cart,
                           total=total,
                           cart_count=cart_count,
                           favorites=favorites,
                           user_logged_in=user_logged_in,
                           exchange_rate=exchange_rate,
                           approx_total_eur=approx_total_eur,
                           is_admin=is_admin)

@app.route('/checkout', methods=['GET', 'POST'])
def checkout():
    """
    Displays the checkout page.
    Passes Stripe publishable key to the template for client-side integration.
    Requires user to be logged in.
    """
    user_id = session.get('user_id')
    if not user_id:
        flash('Будь ласка, увійдіть, щоб оформити замовлення.', 'info')
        return redirect(url_for('login'))

    # Pass cart_count and favorites for display in the top bar
    user_logged_in = session.get('user_id') is not None
    cart_count = sum(item['quantity'] for item in session.get('cart', [])) if user_logged_in else 0
    favorites = session.get('favorites', []) if user_logged_in else []
    is_admin = session.get('is_admin', False)


    return render_template('checkout.html',
                           stripe_public_key=app.config['STRIPE_PUBLISHABLE_KEY'],
                           cart_count=cart_count, favorites=favorites,
                           user_logged_in=user_logged_in,
                           is_admin=is_admin)


@app.route('/create-checkout-session', methods=['POST'])
def create_checkout_session():
    """
    Creates a Stripe Checkout Session for payment processing.
    Calculates prices in EUR based on the current exchange rate.
    Performs stock validation before proceeding.
    Stores recipient name, delivery address, and phone number in session for checkout_success.
    Requires user to be logged in and cart not to be empty.
    """
    user_id = session.get('user_id')
    if not user_id:
        flash('Будь ласка, увійдіть, щоб оформити замовлення.', 'info')
        return redirect(url_for('login'))

    cart = session.get('cart', [])
    if not cart:
        flash('Ваш кошик порожній.', 'info')
        return redirect(url_for('view_cart'))

    db = get_db_connection()

    #Stock Validation
    for item in cart:
        flower = get_flower_by_id(item['id'])
        if not flower:
            flash(f"Товар '{item['name']}' не знайдено.", "danger")
            return redirect(url_for('view_cart'))

        if item['quantity'] > flower['stock']:
            flash(f"На жаль, товару '{item['name']}' є лише {flower['stock']} одиниць в наявності. Оновіть кількість у кошику.", "warning")
            return redirect(url_for('view_cart'))


    exchange_rate = get_uah_to_eur_rate()
    data = request.get_json()
    recipient_name = data.get('recipient_name')
    delivery_address = data.get('delivery_address')
    phone_number = data.get('phone_number')

    #Phone Number Validation
    if not phone_number:
        return jsonify({'error': 'Будь ласка, введіть номер телефону.'}), 400

    cleaned_phone_number = ''.join(filter(str.isdigit, phone_number))
    
    # Check if the cleaned number has a reasonable length (e.g., between 7 and 20 digits)
    if not (7 <= len(cleaned_phone_number) <= 20):
        return jsonify({'error': 'Номер телефону має містити від 7 до 20 цифр.'}), 400

    # Check if all characters are allowed (digits, +, -, (, ))
    allowed_phone_chars = set("0123456789+()- ")
    if not all(char in allowed_phone_chars for char in phone_number):
        return jsonify({'error': 'Номер телефону може містити лише цифри, символи +, -, ( та ).'}), 400

    if not recipient_name or not delivery_address: # Phone number already checked
        return jsonify({'error': 'Будь ласка, заповніть усі поля доставки.'}), 400
    # --- End Advanced Phone Number Validation ---

    # Store delivery details in session to be used in checkout_success
    session['checkout_delivery_details'] = {
        'recipient_name': recipient_name,
        'delivery_address': delivery_address,
        'phone_number_at_purchase': phone_number # Store original formatted number
    }

    line_items = []

    for item in cart:
        price_uah = item['price']
        price_eur = round(price_uah / exchange_rate, 2)
        line_items.append({
            'price_data': {
                'currency': 'eur',
                'product_data': {'name': item['name']},
                'unit_amount': int(price_eur * 100),  # Convert to cents
            },
            'quantity': item['quantity'],
        })

    try:
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=line_items,
            mode='payment',
            success_url=url_for('checkout_success', _external=True) + '?session_id={CHECKOUT_SESSION_ID}',
            cancel_url=url_for('checkout_cancel', _external=True),
        )
        return jsonify({'sessionId': checkout_session.id})
    except stripe.error.StripeError as e:
        # Clear delivery details from session if Stripe checkout creation fails
        session.pop('checkout_delivery_details', None)
        flash(f"Помилка при створенні сесії оплати: {e}", "danger")
        return jsonify({'error': str(e)}), 400


@app.route('/checkout/success')
def checkout_success():
    """
    Handles successful Stripe payment. Clears the user's cart in the database and session.
    Also, *decreases product stock* by ordered quantities and creates an order record,
    including delivery details from the session.
    """
    user_id = session.get('user_id')
    db = get_db_connection()
    cursor = db.cursor()

    cart = session.get('cart', [])
    total_amount = sum(item['price'] * item['quantity'] for item in cart)

    # Retrieve delivery details from session
    delivery_details = session.pop('checkout_delivery_details', None)
    if not delivery_details:
        flash("Помилка: Не вдалося отримати дані доставки. Будь ласка, спробуйте ще раз.", "danger")
        return redirect(url_for('view_cart'))

    recipient_name = delivery_details.get('recipient_name')
    delivery_address = delivery_details.get('delivery_address')
    phone_number_at_purchase = delivery_details.get('phone_number_at_purchase')


    try:
        # 1. Create a new order with all collected details
        cursor.execute(
            "INSERT INTO orders (user_id, total_amount, status, recipient_name, delivery_address, phone_number_at_purchase) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, total_amount, 'Очікується', recipient_name, delivery_address, phone_number_at_purchase)
        )
        order_id = cursor.lastrowid # Get the ID of the newly created order

        # 2. Add items to order_items and decrease product stock
        for item in cart:
            flower_id = item['id']
            ordered_quantity = item['quantity']
            price_at_purchase = item['price'] # Record price at the time of purchase

            cursor.execute(
                "INSERT INTO order_items (order_id, flower_id, quantity, price_at_purchase) VALUES (?, ?, ?, ?)",
                (order_id, flower_id, ordered_quantity, price_at_purchase)
            )

            # Decrease stock for the product
            current_flower = get_flower_by_id(flower_id)
            if current_flower:
                new_stock = current_flower['stock'] - ordered_quantity
                if new_stock < 0: # Should not happen due to prior validation, but as a safeguard
                    new_stock = 0
                cursor.execute("UPDATE products SET stock = ? WHERE id = ?", (new_stock, flower_id))
                print(f"Product {flower_id} stock updated from {current_flower['stock']} to {new_stock}")
            else:
                print(f"Warning: Product {flower_id} not found when trying to update stock.")

        # 3. Clear user's cart after successful payment and order creation
        cursor.execute("DELETE FROM cart_items WHERE user_id = ?", (user_id,))
        db.commit()
        session.pop('cart', None) # Clear cart from session

        flash("Оплата успішна! Дякуємо за замовлення. Ваше замовлення очікує підтвердження.", "success")
        return redirect(url_for('orders_history')) # Redirect to order history

    except Exception as e:
        db.rollback() # Rollback any changes if an error occurs
        flash(f"Помилка при обробці замовлення: {e}", "danger")
        print(f"Error processing order after Stripe success: {e}")
        return redirect(url_for('view_cart'))


@app.route('/checkout/cancel')
def checkout_cancel():
    """Handles Stripe payment cancellation. Also clears delivery details from session."""
    session.pop('checkout_delivery_details', None) # Clear delivery details
    flash("Оплата скасована, ви повернулися до кошика.", "warning")
    return redirect(url_for('view_cart'))


@app.route('/register', methods=['GET', 'POST'])
def register():
    """
    Handles new user registration.
    Performs validation for password match and username uniqueness.
    Phone number input is removed from registration.
    """
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        confirm = request.form.get('confirm')
        # Removed phone_number from registration form data

        if not all([username, password, confirm]): # Check that all fields are filled
            flash("Будь ласка, заповніть усі поля.", "danger")
            return redirect(url_for('register'))
        elif password != confirm:
            flash("Паролі не збігаються.", "danger")
            return redirect(url_for('register'))
        elif len(password) < 6: # Basic password length validation
            flash("Пароль має бути не менше 6 символів.", "danger")
            return redirect(url_for('register'))
        else:
            db = get_db_connection()
            try:
                hashed_password = generate_password_hash(password)
                cursor = db.cursor()
                # Insert user without phone_number
                cursor.execute("INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                               (username, hashed_password, 'user'))
                db.commit()
                flash("Реєстрація успішна! Тепер увійдіть.", "success")
                return redirect(url_for('login'))
            except sqlite3.IntegrityError: # Handle error if user already exists
                flash("Користувач з таким ім'ям вже існує.", "danger")
                db.rollback() # Rollback the failed transaction
                # Force close and remove from g to ensure a clean connection for subsequent operations
                if 'db' in g:
                    g.db.close()
                    del g.db
            except Exception as e:
                flash(f"Помилка реєстрації: {e}", "danger")
                db.rollback()
                # Also force close for general exceptions
                if 'db' in g:
                    g.db.close()
                    del g.db

    user_logged_in = session.get('user_id') is not None
    cart_count = sum(item['quantity'] for item in session.get('cart', [])) if user_logged_in else 0
    favorites = session.get('favorites', []) if user_logged_in else []
    is_admin = session.get('is_admin', False)

    return render_template('register.html',
                           cart_count=cart_count,
                           favorites=favorites,
                           user_logged_in=user_logged_in,
                           is_admin=is_admin)

@app.route('/favorites')
def view_favorites():
    """
    Displays the user's favorite items.
    Requires user to be logged in.
    """
    if not session.get('user_id'):
        flash('Будь ласка, увійдіть, щоб переглянути ваші улюблені товари.', 'info')
        return redirect(url_for('login'))

    favorites = session.get('favorites', []) # Get favorites from session

    # Pass cart_count and favorites for display in the top bar
    user_logged_in = session.get('user_id') is not None
    cart_count = sum(item['quantity'] for item in session.get('cart', [])) if user_logged_in else 0
    is_admin = session.get('is_admin', False)

    return render_template('favorites.html', favorites=favorites,
                           cart_count=cart_count,
                           user_logged_in=user_logged_in,
                           is_admin=is_admin)

@app.route('/add_to_favorites/<int:flower_id>', methods=['POST'])
def add_to_favorites(flower_id):
    """
    Adds an item to the user's favorites list.
    Prevents adding duplicates.
    Requires user to be logged in.
    """
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
        # Update favorites in session by re-loading from DB to ensure consistency
        session['favorites'] = load_user_favorites_from_db(user_id)
        flash(f"{flower['name']} додано в обране.", "success")
    except sqlite3.IntegrityError: # Handle if item is already in favorites (UNIQUE constraint violation)
        flash("Ця квітка вже в обраному.", "info")
        db.rollback()
    except Exception as e:
        flash(f"Помилка додавання до обраного: {e}", "danger")
        db.rollback()

    return redirect(url_for('home'))

@app.route('/remove_from_favorites/<int:flower_id>', methods=['POST'])
def remove_from_favorites(flower_id):
    """
    Removes an item from the user's favorites list.
    Requires user to be logged in.
    """
    user_id = session.get('user_id')
    if not user_id:
        flash('Будь ласка, увійдіть.', 'info')
        return redirect(url_for('login'))

    db = get_db_connection()
    cursor = db.cursor()

    # Get flower name for flash message before potential deletion
    flower_name_cursor = db.execute("SELECT name FROM products WHERE id = ?", (flower_id,)).fetchone()
    flower_name = flower_name_cursor['name'] if flower_name_cursor else "Невідомий товар"

    try:
        cursor.execute("DELETE FROM favorite_items WHERE user_id = ? AND flower_id = ?",
                       (user_id, flower_id))
        db.commit()
        flash(f"Товар \"{flower_name}\" видалено з обраного.", "info")
    except Exception as e:
        flash(f"Помилка при видаленні з обраного: {e}", "danger")
        print(f"Error removing from favorites: {e}")
        db.rollback()

    # Update favorites in session by re-loading from DB to ensure consistency
    session['favorites'] = load_user_favorites_from_db(user_id)
    return redirect(url_for('view_favorites'))

@app.route('/profile')
def profile():
    """
    Displays the user profile page, allowing password changes.
    Requires user to be logged in.
    """
    if not session.get('user_id'):
        flash('Будь ласка, увійдіть, щоб переглянути ваш профіль.', 'info')
        return redirect(url_for('login'))

    username = session.get('username')

    # Load cart and favorites from session for the top bar icons
    user_logged_in = session.get('user_id') is not None
    cart_count = sum(item['quantity'] for item in session.get('cart', [])) if user_logged_in else 0
    favorites = session.get('favorites', []) if user_logged_in else []
    is_admin = session.get('is_admin', False)

    return render_template('profile.html',
                           username=username,
                           cart_count=cart_count,
                           favorites=favorites,
                           user_logged_in=user_logged_in,
                           is_admin=is_admin)

@app.route('/update_password', methods=['POST'])
def update_password():
    """
    Handles updating the user's password.
    Requires user to be logged in and validates old password and new password confirmation.
    """
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
    Jinja2 filter to format a datetime object or "now" string to the specified format.
    Accepts "now" to get the current date.
    Note: This filter does not handle timezone conversion directly.
    Timezone conversion for reviews is handled in get_reviews_for_product.
    """
    if value == 'now':
        return datetime.datetime.now().strftime(format)
    elif isinstance(value, datetime.datetime):
        return value.strftime(format)
    try:
        # Ensure value is treated as string for strptime, then parse
        dt_object = datetime.datetime.strptime(str(value), "%Y-%m-%d %H:%M:%S")
        return dt_object.strftime(format)
    except (TypeError, ValueError):
        # Fallback for unexpected formats, return original value as string
        return str(value)

# Route for viewing product details and reviews
@app.route('/product/<int:product_id>')
def product_detail(product_id):
    """
    Displays the product details page, including its description, price,
    average rating, and user reviews. Allows users to add reviews.
    """
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
    is_admin = session.get('is_admin', False)


    return render_template('product_detail.html',
                           flower=flower,
                           reviews=reviews,
                           average_rating=average_rating,
                           user_logged_in=user_logged_in,
                           cart_count=cart_count,
                           favorites=favorites,
                           user_has_reviewed=user_has_reviewed,
                           is_admin=is_admin)

# Route for adding a review
@app.route('/product/<int:product_id>/add_review', methods=['POST'])
def add_review(product_id):
    """
    Handles adding a new review for a product.
    Validates rating and checks if the user has already reviewed the product.
    Requires user to be logged in.
    """
    user_id = session.get('user_id')
    if not user_id:
        flash('Будь ласка, увійдіть, щоб залишити відгук.', 'info')
        return redirect(url_for('login'))

    rating = request.form.get('rating')
    comment = request.form.get('comment')

    # Check if the user has already left a review for this product
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

@app.route('/delete_review/<int:review_id>', methods=['POST'])
def delete_review(review_id):
    """
    Allows a user to delete their own review.
    Administrators are explicitly prevented from using this route.
    """
    user_id = session.get('user_id')
    if not user_id:
        flash('Будь ласка, увійдіть, щоб видалити відгук.', 'info')
        return redirect(url_for('login'))

    db = get_db_connection()
    cursor = db.cursor()

    review_info = cursor.execute("SELECT user_id, product_id FROM reviews WHERE id = ?", (review_id,)).fetchone()

    if not review_info:
        flash("Відгук не знайдено.", "danger")
        return redirect(url_for('home'))

    # Prevent administrators from deleting reviews using this route
    if session.get('is_admin'):
        flash('Адміністратори не можуть видаляти відгуки через цей інтерфейс.', 'danger')
        return redirect(url_for('product_detail', product_id=review_info['product_id']))


    # Check if the logged-in user is the author of the review
    if review_info['user_id'] != user_id:
        flash("Ви не можете видалити чужий відгук.", "danger")
        return redirect(url_for('product_detail', product_id=review_info['product_id']))

    try:
        cursor.execute("DELETE FROM reviews WHERE id = ?", (review_id,))
        db.commit()
        flash("Відгук успішно видалено.", "success")
    except Exception as e:
        flash(f"Помилка при видаленні відгуку: {e}", "danger")
        db.rollback()

    return redirect(url_for('product_detail', product_id=review_info['product_id']))

@app.route('/orders_history')
def orders_history():
    """
    Displays the current user's order history.
    Requires user to be logged in.
    """
    user_id = session.get('user_id')
    if not user_id:
        flash('Будь ласка, увійдіть, щоб переглянути історію замовлень.', 'info')
        return redirect(url_for('login'))

    db = get_db_connection()
    cursor = db.cursor()

    # Fetch all orders for the current user
    orders_data = cursor.execute(
        "SELECT id, total_amount, status, created_at FROM orders WHERE user_id = ? ORDER BY created_at DESC",
        (user_id,)
    ).fetchall()

    orders = []
    kyiv_offset = datetime.timedelta(hours=3)

    for order_row in orders_data:
        order_id = order_row['id']
        # Fetch items for each order
        order_items_data = cursor.execute(
            """
            SELECT oi.quantity, oi.price_at_purchase, p.name, p.image_url
            FROM order_items oi
            JOIN products p ON oi.flower_id = p.id
            WHERE oi.order_id = ?
            """,
            (order_id,)
        ).fetchall()

        items = []
        for item_row in order_items_data:
            items.append({
                'name': item_row['name'],
                'quantity': item_row['quantity'],
                'price_at_purchase': item_row['price_at_purchase'],
                'image_url': item_row['image_url']
            })

        # Format created_at to Kyiv time
        try:
            utc_dt = datetime.datetime.strptime(order_row['created_at'], "%Y-%m-%d %H:%M:%S")
            kyiv_dt = utc_dt + kyiv_offset
            formatted_time = kyiv_dt.strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            formatted_time = order_row['created_at'] # Fallback

        orders.append({
            'id': order_row['id'],
            'total_amount': order_row['total_amount'],
            'status': order_row['status'],
            'created_at': formatted_time,
            'items': items
        })

    # Pass cart_count and favorites for display in the top bar
    user_logged_in = session.get('user_id') is not None
    cart_count = sum(item['quantity'] for item in session.get('cart', [])) if user_logged_in else 0
    favorites = session.get('favorites', []) if user_logged_in else []
    is_admin = session.get('is_admin', False)


    return render_template('orders_history.html',
                           orders=orders,
                           cart_count=cart_count,
                           favorites=favorites,
                           user_logged_in=user_logged_in,
                           is_admin=is_admin)

@app.route('/admin/orders')
def admin_orders():
    """
    Displays all orders for administrators, allowing them to change order status.
    Requires administrator privileges.
    """
    if not session.get('is_admin'):
        flash('Доступ заборонено. Тільки адміністратори можуть переглядати замовлення.', 'danger')
        return redirect(url_for('login'))

    db = get_db_connection()
    cursor = db.cursor()

    # Fetch all orders with user information including recipient_name, delivery_address, phone_number_at_purchase
    all_orders_data = cursor.execute(
        """
        SELECT o.id, o.total_amount, o.status, o.created_at, u.username, o.recipient_name, o.delivery_address, o.phone_number_at_purchase
        FROM orders o
        JOIN users u ON o.user_id = u.id
        ORDER BY o.created_at DESC
        """
    ).fetchall()

    orders = []
    kyiv_offset = datetime.timedelta(hours=3)

    for order_row in all_orders_data:
        order_id = order_row['id']
        # Fetch items for each order
        order_items_data = cursor.execute(
            """
            SELECT oi.quantity, oi.price_at_purchase, p.name, p.image_url
            FROM order_items oi
            JOIN products p ON oi.flower_id = p.id
            WHERE oi.order_id = ?
            """,
            (order_id,)
        ).fetchall()

        items = []
        for item_row in order_items_data:
            items.append({
                'name': item_row['name'],
                'quantity': item_row['quantity'],
                'price_at_purchase': item_row['price_at_purchase'],
                'image_url': item_row['image_url']
            })

        # Format created_at to Kyiv time
        try:
            utc_dt = datetime.datetime.strptime(order_row['created_at'], "%Y-%m-%d %H:%M:%S")
            kyiv_dt = utc_dt + kyiv_offset
            formatted_time = kyiv_dt.strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            formatted_time = order_row['created_at'] # Fallback

        orders.append({
            'id': order_row['id'],
            'username': order_row['username'],
            'recipient_name': order_row['recipient_name'],
            'delivery_address': order_row['delivery_address'],
            'phone_number_at_purchase': order_row['phone_number_at_purchase'],
            'total_amount': order_row['total_amount'],
            'status': order_row['status'],
            'created_at': formatted_time,
            'items': items
        })

    user_logged_in = session.get('user_id') is not None
    cart_count = sum(item['quantity'] for item in session.get('cart', [])) if user_logged_in else 0
    favorites = session.get('favorites', []) if user_logged_in else []
    is_admin = session.get('is_admin', False)


    return render_template('admin_orders.html',
                           orders=orders,
                           cart_count=cart_count,
                           favorites=favorites,
                           user_logged_in=user_logged_in,
                           is_admin=is_admin)

@app.route('/admin_dashboard')
def admin_dashboard():
    """
    Displays the admin dashboard.
    Only accessible by logged-in administrators.
    """
    if not session.get('is_admin'):
        flash('Доступ заборонено. Тільки адміністратори мають доступ до адмін-панелі.', 'danger')
        return redirect(url_for('login'))

    user_logged_in = session.get('user_id') is not None
    cart_count = sum(item['quantity'] for item in session.get('cart', [])) if user_logged_in else 0
    favorites = session.get('favorites', []) if user_logged_in else []
    is_admin = session.get('is_admin', False)


    return render_template('admin_dashboard.html',
                           cart_count=cart_count,
                           favorites=favorites,
                           user_logged_in=user_logged_in,
                           is_admin=is_admin)

@app.route('/admin/update_order_status/<int:order_id>', methods=['POST'])
def update_order_status(order_id):
    """
    Updates the status of a specific order.
    Requires administrator privileges.
    """
    if not session.get('is_admin'):
        flash('Доступ заборонено. Тільки адміністратори можуть оновлювати статус замовлень.', 'danger')
        return redirect(url_for('login'))

    new_status = request.form.get('status')
    if new_status not in ['Очікується', 'Підтверджено']:
        flash('Недійсний статус замовлення.', 'danger')
        return redirect(url_for('admin_orders'))

    db = get_db_connection()
    cursor = db.cursor()

    try:
        cursor.execute("UPDATE orders SET status = ? WHERE id = ?", (new_status, order_id))
        db.commit()
        flash(f"Статус замовлення №{order_id} оновлено на '{new_status}'.", "success")
    except Exception as e:
        flash(f"Помилка при оновленні статусу замовлення: {e}", "danger")
        db.rollback()

    return redirect(url_for('admin_orders'))

# --- TEST ROUTE FOR MANUAL ORDER CREATION (FOR DEVELOPMENT ONLY) ---
@app.route('/create_test_order', methods=['GET'])
def create_test_order():
    """
    [DEVELOPMENT ONLY]
    Creates a test order for the current logged-in user with items from their cart.
    Bypasses Stripe payment. Decreases product stock.
    This route should be REMOVED or PROTECTED in a production environment.
    """
    user_id = session.get('user_id')
    if not user_id:
        flash('Будь ласка, увійдіть як користувач, щоб створити тестове замовлення.', 'info')
        return redirect(url_for('login'))

    db = get_db_connection()
    cursor = db.cursor()

    # Get current user's cart
    cart = load_user_cart_from_db(user_id)
    if not cart:
        flash('Ваш кошик порожній. Додайте товари, щоб створити тестове замовлення.', 'warning')
        return redirect(url_for('home'))

    total_amount = sum(item['price'] * item['quantity'] for item in cart)

    # For test order, dummy delivery details
    recipient_name = "Стасько Тарас"
    delivery_address = "Шевченка вул. 1, місто Київ, 02000"
    phone_number_at_purchase = "+380991234567"


    try:
        # 1. Create a new order with 'Очікується' status and delivery details
        cursor.execute(
            "INSERT INTO orders (user_id, total_amount, status, recipient_name, delivery_address, phone_number_at_purchase) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, total_amount, 'Очікується', recipient_name, delivery_address, phone_number_at_purchase)
        )
        order_id = cursor.lastrowid # Get the ID of the newly created order

        # 2. Add items to order_items and decrease product stock
        for item in cart:
            flower_id = item['id']
            ordered_quantity = item['quantity']
            price_at_purchase = item['price']

            # Check stock before creating the order
            current_flower = get_flower_by_id(flower_id)
            if not current_flower or current_flower['stock'] < ordered_quantity:
                flash(f"Недостатньо товару '{item['name']}' для тестового замовлення. В наявності: {current_flower['stock'] if current_flower else 0}.", 'danger')
                db.rollback() # Rollback the order creation if stock is insufficient
                return redirect(url_for('view_cart')) # Redirect back to cart or home

            cursor.execute(
                "INSERT INTO order_items (order_id, flower_id, quantity, price_at_purchase) VALUES (?, ?, ?, ?)",
                (order_id, flower_id, ordered_quantity, price_at_purchase)
            )

            # Decrease stock
            new_stock = current_flower['stock'] - ordered_quantity
            cursor.execute("UPDATE products SET stock = ? WHERE id = ?", (new_stock, flower_id))
            print(f"Test Order: Product {flower_id} stock updated from {current_flower['stock']} to {new_stock}")

        # 3. Clear user's cart
        cursor.execute("DELETE FROM cart_items WHERE user_id = ?", (user_id,))
        db.commit()
        session.pop('cart', None) # Clear cart from session

        flash(f"Тестове замовлення №{order_id} успішно створено!.", "success")
        return redirect(url_for('orders_history'))

    except Exception as e:
        db.rollback()
        flash(f"Помилка при створенні тестового замовлення: {e}", "danger")
        print(f"Error creating test order: {e}")
        return redirect(url_for('home'))

# --- END TEST ROUTE ---


if __name__ == '__main__':
    app.run(debug=True)
