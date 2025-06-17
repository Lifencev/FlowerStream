from flask import Flask, render_template, request, redirect, url_for, flash, session, g, jsonify
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
import datetime
import os
import stripe
from config import Config
from dotenv import load_dotenv
from werkzeug.utils import secure_filename
import uuid

load_dotenv()

app = Flask(__name__)
app.config.from_object(Config)
stripe.api_key = app.config['STRIPE_SECRET_KEY']
DATABASE = os.getenv('DATABASE')

UPLOAD_FOLDER = 'static/images'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

full_upload_path = os.path.join(app.root_path, UPLOAD_FOLDER)
if not os.path.exists(full_upload_path):
    try:
        os.makedirs(full_upload_path)
        print(f"Створено папку для завантажень: {full_upload_path}")
    except OSError as e:
        print(f"Помилка при створенні папки для завантажень {full_upload_path}: {e}")
        flash(f"Помилка сервера: не вдалося створити папку для завантажень. {e}", "danger")


def allowed_file(filename):
    """
    Перевіряє, чи дозволено розширення файлу.
    """
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_db_connection():
    """
    Отримує з'єднання з базою даних. 
    Використовує об'єкт 'g' Flask для кешування з'єднання протягом запиту.
    """
    db = getattr(g, '_database', None)
    if db is None:
        db = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_connection(exception):
    """Закриває з'єднання з базою даних після завершення запиту."""
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def init_db():
    """
    Ініціалізує базу даних: створює необхідні таблиці (users, products, cart_items, favorite_items)
    та додає початкові дані (адміністратора, квіти), якщо їх немає.
    """
    db = get_db_connection()
    cursor = db.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'user'
            )
        ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            price REAL NOT NULL,
            image_url TEXT
        )
    ''')

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
    db.commit()

    cursor.execute("SELECT COUNT(*) FROM users WHERE username = 'admin'")
    if cursor.fetchone()[0] == 0:
        hashed_password = generate_password_hash('admin123') 
        cursor.execute("INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                       ('admin', hashed_password, 'admin'))
        db.commit()
        print("Адміністратора за замовчуванням додано (логін: admin, пароль: admin123)")
    
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
            }
        ]
        for flower in initial_flowers_data:
            cursor.execute("INSERT INTO products (name, description, price, image_url) VALUES (?, ?, ?, ?)",
                           (flower['name'], flower['description'], flower['price'], flower['image_url']))
        db.commit()
        print("Початкові квіти додано до бази даних.")
    
    print("База даних ініціалізована.")

with app.app_context():
    init_db()


def load_products_from_db():
    """Завантажує всі товари (квіти) з таблиці products."""
    db = get_db_connection()
    cursor = db.execute("SELECT * FROM products ORDER BY id ASC")
    return cursor.fetchall()

def get_flower_by_id(flower_id):
    """Повертає об'єкт квітки за ID з БД."""
    db = get_db_connection()
    cursor = db.execute("SELECT * FROM products WHERE id = ?", (flower_id,))
    return cursor.fetchone()



def load_user_cart_from_db(user_id):
    """Завантажує кошик користувача з БД та повертає у форматі сесії."""
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
    """Зберігає кошик користувача з сесії в БД."""
    db = get_db_connection()
    cursor = db.cursor()
    cursor.execute("DELETE FROM cart_items WHERE user_id = ?", (user_id,))
    for item in cart_data:
        cursor.execute("INSERT INTO cart_items (user_id, flower_id, quantity) VALUES (?, ?, ?)",
                       (user_id, item['id'], item['quantity']))
    db.commit()

def load_user_favorites_from_db(user_id):
    """Завантажує обране користувача з БД та повертає у форматі сесії."""
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
    """Зберігає обране користувача з сесії в БД."""
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
    
    flowers = load_products_from_db() 

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
                           user_logged_in=user_logged_in, edit_mode=edit_mode)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        db = get_db_connection()
        user = db.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()

        if user and check_password_hash(user['password_hash'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['is_admin'] = (user['role'] == 'admin') 
            
            session['cart'] = load_user_cart_from_db(user['id'])
            session['favorites'] = load_user_favorites_from_db(user['id'])
            
            session['edit_mode'] = False 

            flash('Успішний вхід!', 'success')
            return redirect(url_for('home'))
        else:
            flash('Невірні логін або пароль.', 'danger')
    
    return render_template('admin_login.html') 

@app.route('/logout')
def logout():
    user_id = session.get('user_id')
    if user_id:
        save_user_cart_to_db(user_id, session.get('cart', []))
        save_user_favorites_to_db(user_id, session.get('favorites', []))

    session.pop('user_id', None)
    session.pop('username', None)
    session.pop('is_admin', None) 
    session.pop('cart', None)       
    session.pop('favorites', None)  
    session.pop('edit_mode', None)  
    flash('Ви вийшли з системи.', 'info')
    return redirect(url_for('home'))

@app.route('/toggle_edit_mode', methods=['POST'])
def toggle_edit_mode():
    if not session.get('is_admin'):
        flash('Доступ заборонено. Тільки адміністратори можуть перемикати режим редагування.', 'danger')
        return redirect(url_for('login'))
    
    session['edit_mode'] = not session.get('edit_mode', False) 
    flash(f"Режим редагування: {'увімкнено' if session['edit_mode'] else 'вимкнено'}.", 'info')
    return redirect(url_for('home'))


@app.route('/edit_flower/<int:flower_id>', methods=['POST'])
def edit_flower(flower_id):
    """
    Редагує існуючий товар. Додано можливість завантаження нового зображення 
    та видалення старого зображення.
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

    current_flower = get_flower_by_id(flower_id)
    old_image_url = current_flower['image_url'] if current_flower else None
    new_image_url = old_image_url

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
                print(f"Нове зображення збережено: {file_path}. URL для БД: {new_image_url}")

                if old_image_url and "static/images/flower" not in old_image_url:
                    old_file_path = os.path.join(app.root_path, old_image_url)
                    if os.path.exists(old_file_path):
                        try:
                            os.remove(old_file_path)
                            print(f"Старе зображення видалено: {old_file_path}")
                        except OSError as e:
                            print(f"Помилка при видаленні старого зображення {old_file_path}: {e}")
                            flash(f"Помилка при видаленні старого зображення: {e}", "warning")
            except Exception as e:
                flash(f"Помилка при завантаженні нового зображення: {e}", "danger")
                print(f"Помилка завантаження зображення: {e}")
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
        print(f"Помилка БД при оновленні товару: {e}")
        db.rollback()

    return redirect(url_for('home'))


@app.route('/delete_flower/<int:flower_id>', methods=['POST'])
def delete_flower(flower_id):
    """
    Видаляє товар з бази даних та пов'язане зображення.
    Тільки для адміністраторів у режимі редагування.
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
        cursor.execute("DELETE FROM products WHERE id = ?", (flower_id,))
        db.commit()

        if flower['image_url'] and "static/images/flower" not in flower['image_url']: # Пропускаємо початкові зображення
            file_path = os.path.join(app.root_path, flower['image_url'])
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                    print(f"Зображення видалено: {file_path}")
                except OSError as e:
                    print(f"Помилка при видаленні зображення {file_path}: {e}")
                    flash(f"Помилка при видаленні зображення товару: {e}", "warning")
        
        flash(f"Товар \"{flower['name']}\" успішно видалено.", "success")
    except Exception as e:
        flash(f"Помилка при видаленні товару: {e}", "danger")
        print(f"Помилка БД при видаленні товару: {e}")
        db.rollback()

    return redirect(url_for('home'))


@app.route('/add_flower', methods=['POST'])
def add_flower():
    """
    Додає новий товар (квітку) до бази даних.
    Тільки для адміністраторів у режимі редагування.
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
                unique_filename = f"{uuid.uuid4().hex}.{file_ext}"
                
                file_path = os.path.join(app.root_path, app.config['UPLOAD_FOLDER'], unique_filename)
                
                os.makedirs(os.path.dirname(file_path), exist_ok=True)

                image_file.save(file_path)
                
                image_url = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename).replace("\\", "/")
                flash(f"Файл '{original_filename}' успішно завантажено.", "success")
                print(f"Зображення збережено: {file_path}. URL для БД: {image_url}")
            except Exception as e:
                flash(f"Помилка при збереженні зображення: {e}", "danger")
                print(f"Помилка збереження зображення: {e}")
                return redirect(url_for('home'))
        else:
            flash("Недопустимий формат файлу зображення.", "danger")
            return redirect(url_for('home'))
    else:
        flash("Товар буде додано без зображення.", "info")
        print("Зображення не було надано або файл був порожнім.")


    db = get_db_connection()
    cursor = db.cursor()
    try:
        cursor.execute("INSERT INTO products (name, description, price, image_url) VALUES (?, ?, ?, ?)",
                       (name, description, price, image_url))
        db.commit()
        flash(f"Товар \"{name}\" успішно додано.", "success")
        print(f"Товар '{name}' додано до БД з URL: {image_url}")
    except Exception as e:
        flash(f"Помилка при додаванні товару до бази даних: {e}", "danger")
        print(f"Помилка БД при додаванні товару: {e}")
        db.rollback()
    
    return redirect(url_for('home'))


@app.route('/add_to_cart/<int:flower_id>', methods=['POST'])
def add_to_cart(flower_id):
    user_id = session.get('user_id')
    if not user_id:
        flash('Будь ласка, увійдіть, щоб додати товари до кошика.', 'info')
        return redirect(url_for('login'))

    flower = get_flower_by_id(flower_id) 
    if not flower:
        flash('Квітка не знайдена.', 'danger')
        return redirect(url_for('home'))

    db = get_db_connection()
    cursor = db.cursor()
    
    cursor.execute("SELECT quantity FROM cart_items WHERE user_id = ? AND flower_id = ?", (user_id, flower_id))
    existing_item_db = cursor.fetchone()

    if existing_item_db:
        new_quantity = existing_item_db['quantity'] + 1
        cursor.execute("UPDATE cart_items SET quantity = ? WHERE user_id = ? AND flower_id = ?",
                       (new_quantity, user_id, flower_id))
        flash(f"{flower['name']} кількість збільшено до {new_quantity}.", "success")
    else:
        cursor.execute("INSERT INTO cart_items (user_id, flower_id, quantity) VALUES (?, ?, ?)",
                       (user_id, flower_id, 1))
        flash(f"{flower['name']} додано до кошика.", "success")
    db.commit()

    session['cart'] = load_user_cart_from_db(user_id)
    return redirect(url_for('home'))

@app.route('/remove_from_cart/<int:index>', methods=['POST'])
def remove_from_cart(index):
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

        session['cart'] = load_user_cart_from_db(user_id)
        flash(f"{removed_item['name']} видалено з кошика.", "info")
    else:
        flash("Товар не знайдено в кошику.", "danger")
    return redirect(url_for('view_cart'))

@app.route('/increase_quantity/<int:index>', methods=['POST'])
def increase_quantity(index):
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
        
        session['cart'] = load_user_cart_from_db(user_id)
    return redirect(url_for('view_cart'))

@app.route('/decrease_quantity/<int:index>', methods=['POST'])
def decrease_quantity(index):
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
        
        session['cart'] = load_user_cart_from_db(user_id)
    return redirect(url_for('view_cart'))

@app.route('/cart')
def view_cart():
    if not session.get('user_id'):
        flash('Будь ласка, увійдіть, щоб переглянути ваш кошик.', 'info')
        return redirect(url_for('login'))
        
    cart = session.get('cart', [])
    total = sum(item['price'] * item['quantity'] for item in cart)
    return render_template('cart.html', cart=cart, total=total)

@app.route('/checkout', methods=['GET', 'POST'])
def checkout():
    user_id = session.get('user_id')
    if not user_id:
        flash('Будь ласка, увійдіть, щоб оформити замовлення.', 'info')
        return redirect(url_for('login'))

    return render_template('checkout.html',
                           publishable_key=app.config['STRIPE_PUBLISHABLE_KEY'])


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

    line_items = []
    for item in cart:
        line_items.append({
            'price_data': {
                'currency': 'eur',
                'product_data': {'name': item['name']},
                'unit_amount': int(item['price'] * 100),
            },
            'quantity': item['quantity'],
        })

    checkout_session = stripe.checkout.Session.create(
        payment_method_types=['card'],
        line_items=line_items,
        mode='payment',
        success_url=url_for('checkout_success', _external=True)
                    + '?session_id={CHECKOUT_SESSION_ID}',
        cancel_url=url_for('checkout_cancel', _external=True),
    )

    return jsonify({'sessionId': checkout_session.id})


@app.route('/checkout/success')
def checkout_success():
    user_id = session.get('user_id')
    db = get_db_connection()
    db.execute("DELETE FROM cart_items WHERE user_id = ?", (user_id,))
    db.commit()
    session.pop('cart', None)
    flash("Оплата успішна! Дякуємо за замовлення.", "success")
    return redirect(url_for('home'))

@app.route('/checkout/cancel')
def checkout_cancel():
    flash("Оплата скасована, ви повернутися до кошика.", "warning")
    return redirect(url_for('view_cart'))


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        confirm = request.form.get('confirm')

        if not username or not password or not confirm:
            flash("Будь ласка, заповніть усі поля.", "danger")
        elif password != confirm:
            flash("Паролі не збігаються.", "danger")
        else:
            db = get_db_connection()
            try:
                hashed_password = generate_password_hash(password)
                db.execute("INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                           (username, hashed_password, 'user')) 
                db.commit()
                flash("Реєстрація успішна! Тепер увійдіть.", "success") 
                return redirect(url_for('login'))
            except sqlite3.IntegrityError:
                flash("Користувач з таким ім'ям вже існує.", "danger")
            except Exception as e:
                flash(f"Помилка реєстрації: {e}", "danger")
                db.rollback() 

    return render_template('register.html')

@app.route('/favorites')
def view_favorites():
    if not session.get('user_id'):
        flash('Будь ласка, увійдіть, щоб переглянути ваші улюблені товари.', 'info')
        return redirect(url_for('login'))

    favorites = session.get('favorites', [])
    return render_template('favorites.html', favorites=favorites)

@app.route('/add_to_favorites/<int:flower_id>', methods=['POST'])
def add_to_favorites(flower_id):
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
        session['favorites'] = load_user_favorites_from_db(user_id)
        flash(f"{flower['name']} додано в обране.", "success")
    except sqlite3.IntegrityError:
        flash("Ця квітка вже в обраному.", "info")
        db.rollback() 
    except Exception as e:
        flash(f"Помилка додавання до обраного: {e}", "danger")
        db.rollback()
    
    return redirect(url_for('home'))

@app.route('/remove_from_favorites/<int:flower_id>', methods=['POST'])
def remove_from_favorites(flower_id):
    user_id = session.get('user_id')
    if not user_id:
        flash('Будь ласка, увійдіть.', 'info')
        return redirect(url_for('login'))

    db = get_db_connection()
    cursor = db.cursor()
    
    flower_name_cursor = db.execute("SELECT name FROM products WHERE id = ?", (flower_id,)).fetchone()
    flower_name = flower_name_cursor['name'] if flower_name_cursor else "Невідомий товар"

    cursor.execute("DELETE FROM favorite_items WHERE user_id = ? AND flower_id = ?",
                   (user_id, flower_name_cursor['id']))
    db.commit()

    session['favorites'] = load_user_favorites_from_db(user_id)
    flash(f"Товар \"{flower_name}\" видалено з обраного.", "info") 
    return redirect(url_for('view_favorites'))

@app.route('/profile')
def profile():
    if not session.get('user_id'):
        flash('Будь ласка, увійдіть, щоб переглянути ваш профіль.', 'info')
        return redirect(url_for('login'))

    username = session.get('username')
    
    return render_template('profile.html', username=username)

@app.route('/update_password', methods=['POST'])
def update_password():
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
    Форматує об'єкт datetime або рядок "now" у заданий формат.
    Приймає значення "now" для отримання поточної дати.
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


if __name__ == '__main__':
    app.run(debug=True)