from flask import Flask, render_template, request, redirect, url_for, flash, session

app = Flask(__name__)
app.secret_key = 'very_secret_key'

flowers = [
    {
        'id': 1,
        'name': 'Троянда червона',
        'description': 'Класична червона троянда – символ любові.',
        'price': 150,
        'image_url': 'https://via.placeholder.com/200x150.png?text=Rose'
    },
    {
        'id': 2,
        'name': 'Тюльпан жовтий',
        'description': 'Яскравий тюльпан для гарного настрою.',
        'price': 90,
        'image_url': 'https://via.placeholder.com/200x150.png?text=Tulip'
    },
    {
        'id': 3,
        'name': 'Лілія біла',
        'description': 'Ніжна біла лілія – вишуканий подарунок.',
        'price': 120,
        'image_url': 'https://via.placeholder.com/200x150.png?text=Lily'
    }
]

@app.route('/')
def home():
    is_admin = session.get('admin_logged_in', False)
    cart = session.get('cart', [])
    cart_count = sum(item['quantity'] for item in cart) if cart else 0
    favorites = session.get('favorites', [])
    return render_template('home.html', flowers=flowers, is_admin=is_admin, cart_count=cart_count, favorites=favorites)

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        if username == 'admin' and password == 'admin123':
            session['admin_logged_in'] = True
            flash('Успішний вхід!', 'success')
            return redirect(url_for('home'))
        else:
            flash('Невірні дані', 'danger')
    return render_template('admin_login.html')

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_logged_in', None)
    flash('Ви вийшли з системи.', 'info')
    return redirect(url_for('home'))

@app.route('/edit/<int:flower_id>', methods=['POST'])
def edit_flower(flower_id):
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))

    for flower in flowers:
        if flower['id'] == flower_id:
            flower['name'] = request.form['name']
            flower['description'] = request.form['description']
            flower['price'] = float(request.form['price'])
            flash(f"Квітка #{flower_id} оновлена.", "success")
            break
    return redirect(url_for('home'))

@app.route('/add_to_cart/<int:flower_id>', methods=['POST'])
def add_to_cart(flower_id):
    flower = next((f for f in flowers if f['id'] == flower_id), None)
    if flower:
        cart = session.get('cart', [])
        # Перевіряємо, чи товар вже у кошику
        existing_item = next((item for item in cart if item['id'] == flower_id), None)
        if existing_item:
            existing_item['quantity'] += 1
        else:
            item_to_add = flower.copy()
            item_to_add['quantity'] = 1
            cart.append(item_to_add)
        session['cart'] = cart
        flash(f"{flower['name']} додано до кошика.", "success")
    return redirect(url_for('home'))

@app.route('/remove_from_cart/<int:index>', methods=['POST'])
def remove_from_cart(index):
    cart = session.get('cart', [])
    if 0 <= index < len(cart):
        removed = cart.pop(index)
        session['cart'] = cart
        flash(f"{removed['name']} видалено з кошика.", "info")
    return redirect(url_for('view_cart'))

@app.route('/increase_quantity/<int:index>', methods=['POST'])
def increase_quantity(index):
    cart = session.get('cart', [])
    if 0 <= index < len(cart):
        cart[index]['quantity'] += 1
        session['cart'] = cart
    return redirect(url_for('view_cart'))

@app.route('/decrease_quantity/<int:index>', methods=['POST'])
def decrease_quantity(index):
    cart = session.get('cart', [])
    if 0 <= index < len(cart):
        if cart[index]['quantity'] > 1:
            cart[index]['quantity'] -= 1
            session['cart'] = cart
    return redirect(url_for('view_cart'))

@app.route('/cart')
def view_cart():
    cart = session.get('cart', [])
    total = sum(item['price'] * item['quantity'] for item in cart)
    return render_template('cart.html', cart=cart, total=total)

@app.route('/checkout', methods=['GET', 'POST'])
def checkout():
    if request.method == 'POST':
        name = request.form.get('full_name')
        address = request.form.get('address')
        notes = request.form.get('notes')
        agree = request.form.get('agree')

        if not all([name, address, agree]):
            flash("Заповніть обов'язкові поля та погодьтесь з умовами.", "danger")
            return redirect(url_for('checkout'))

        session.pop('cart', None)
        flash("Замовлення оформлено! Дякуємо!", "success")
        return redirect(url_for('home'))

    return render_template('checkout.html')

users = {}

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
            # Тут можна зберігати користувача (наприклад, у базу або файл)
            flash("Реєстрація успішна! Тепер увійдіть.", "success")
            return redirect(url_for('admin_login'))
    return render_template('register.html')


# --- Favorites routes ---

@app.route('/favorites')
def view_favorites():
    favorites = session.get('favorites', [])
    return render_template('favorites.html', favorites=favorites)

@app.route('/add_to_favorites/<int:flower_id>', methods=['POST'])
def add_to_favorites(flower_id):
    favorites = session.get('favorites', [])
    flower = next((f for f in flowers if f['id'] == flower_id), None)
    if flower and all(f['id'] != flower_id for f in favorites):
        favorites.append(flower)
        session['favorites'] = favorites
        flash(f"{flower['name']} додано в обране.", "success")
    else:
        flash("Ця квітка вже в обраному.", "info")
    return redirect(url_for('home'))

@app.route('/remove_from_favorites/<int:flower_id>', methods=['POST'])
def remove_from_favorites(flower_id):
    favorites = session.get('favorites', [])
    favorites = [f for f in favorites if f['id'] != flower_id]
    session['favorites'] = favorites
    flash("Товар видалено з обраного.", "info")
    return redirect(url_for('view_favorites'))

if __name__ == '__main__':
    app.run(debug=True)
