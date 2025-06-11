from flask import Flask, render_template, request, redirect, url_for, flash, session

app = Flask(__name__)
app.secret_key = 'very_secret_key'

# 🔸 Дані квітів (імітація БД)
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

# 🔹 Головна
@app.route('/')
def home():
    is_admin = session.get('admin_logged_in', False)
    cart = session.get('cart', [])
    favorites = session.get('favorites', [])
    cart_count = len(cart)
    fav_count = len(favorites)
    return render_template('home.html', 
                         flowers=flowers, 
                         is_admin=is_admin, 
                         cart_count=cart_count,
                         favorites=favorites,
                         fav_count=fav_count)

# 🔹 Авторизація
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

# 🔹 Вихід
@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_logged_in', None)
    flash('Ви вийшли з системи.', 'info')
    return redirect(url_for('home'))

# 🔹 Редагування (адмін)
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

# 🔹 Додавання до кошика
@app.route('/add_to_cart/<int:flower_id>', methods=['POST'])
def add_to_cart(flower_id):
    flower = next((f for f in flowers if f['id'] == flower_id), None)
    if not flower:
        return redirect(url_for('home'))

    cart = session.get('cart', [])

    # Перевіряємо, чи товар вже є в кошику
    found_item = False
    for item in cart:
        if item['id'] == flower_id:
            item['quantity'] = item.get('quantity', 0) + 1
            found_item = True
            break
    
    if not found_item:
        # Якщо товару немає, додаємо новий
        cart.append({
            'id': flower['id'],
            'name': flower['name'],
            'price': flower['price'],
            'image_url': flower['image_url'],
            'description': flower['description'],
            'quantity': 1  # Початкова кількість
        })

    session['cart'] = cart
    flash(f"{flower['name']} додано до кошика.", "success")
    return redirect(url_for('home'))

# 🔹 Перегляд кошика
@app.route('/cart')
def view_cart():
    cart = session.get('cart', [])
    total = sum(item['price'] * item.get('quantity', 1) for item in cart)
    
    # Optional: Clean up cart items that are missing quantity
    for item in cart:
        if 'quantity' not in item:
            item['quantity'] = 1
    session['cart'] = cart
    
    return render_template('cart.html', cart=cart, total=total)

# 🔹 Збільшення кількості товару
@app.route('/increase_quantity/<int:index>', methods=['POST'])
def increase_quantity(index):
    cart = session.get('cart', [])
    if 0 <= index < len(cart):
        cart[index]['quantity'] = cart[index].get('quantity', 0) + 1
        session['cart'] = cart
        flash(f"Кількість товару '{cart[index]['name']}' збільшено.", "info")
    return redirect(url_for('view_cart'))

# 🔹 Зменшення кількості товару
@app.route('/decrease_quantity/<int:index>', methods=['POST'])
def decrease_quantity(index):
    cart = session.get('cart', [])
    if 0 <= index < len(cart):
        current_quantity = cart[index].get('quantity', 1)
        if current_quantity > 1:
            cart[index]['quantity'] = current_quantity - 1
            flash(f"Кількість товару '{cart[index]['name']}' зменшено.", "info")
        else:
            # Видаляємо товар, якщо кількість стає 0 або менше
            removed = cart.pop(index)
            flash(f"{removed['name']} повністю видалено з кошика.", "info")
        session['cart'] = cart
    return redirect(url_for('view_cart'))

# 🔹 Видалення товару з кошика
@app.route('/remove_from_cart/<int:index>', methods=['POST'])
def remove_from_cart(index):
    cart = session.get('cart', [])
    if 0 <= index < len(cart):
        removed = cart.pop(index)
        flash(f"{removed['name']} повністю видалено з кошика.", "info")
        session['cart'] = cart
    return redirect(url_for('view_cart'))

# 🔹 Оформлення замовлення
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

# 🔹 Перегляд обраного
@app.route('/favorites')
def view_favorites():
    favorites = session.get('favorites', [])
    return render_template('favorites.html', favorites=favorites)

# 🔹 Додавання до обраного
@app.route('/add_to_favorites/<int:flower_id>', methods=['POST'])
def add_to_favorites(flower_id):
    flower = next((f for f in flowers if f['id'] == flower_id), None)
    if not flower:
        return redirect(url_for('home'))

    favorites = session.get('favorites', [])

    if not any(f['id'] == flower_id for f in favorites):
        favorites.append({
            'id': flower['id'],
            'name': flower['name'],
            'price': flower['price'],
            'image_url': flower['image_url'],
            'description': flower['description']
        })
        session['favorites'] = favorites
        flash(f"{flower['name']} додано до обраного.", "success")
    else:
        flash(f"{flower['name']} вже є в обраному.", "info")

    return redirect(url_for('home'))

# 🔹 Видалення з обраного
@app.route('/remove_from_favorites/<int:flower_id>', methods=['POST'])
def remove_from_favorites(flower_id):
    favorites = session.get('favorites', [])
    updated_favorites = [f for f in favorites if f['id'] != flower_id]
    
    if len(updated_favorites) < len(favorites):
        session['favorites'] = updated_favorites
        flower = next((f for f in flowers if f['id'] == flower_id), None)
        if flower:
            flash(f"{flower['name']} видалено з обраного.", "info")
    else:
        flash("Товар не знайдено в обраному.", "warning")
    
    return redirect(url_for('view_favorites'))


if __name__ == '__main__':
    app.run(debug=True)