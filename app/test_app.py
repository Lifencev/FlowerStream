import unittest
from app import app, flowers
from flask import get_flashed_messages


class FlaskAppTests(unittest.TestCase):

    # Цей метод виконується перед кожним тестом
    def setUp(self):
        app.config['TESTING'] = True
        app.config['WTF_CSRF_ENABLED'] = False
        app.config['DEBUG'] = False
        self.app = app.test_client()
        with self.app as client:
            with client.session_transaction() as sess:
                sess.clear()
        print(f"\n--- Початок тесту: {self._testMethodName} ---")  # Додаємо вивід початку тесту

    # Цей метод виконується після кожного тесту
    def tearDown(self):
        print(f"--- Кінець тесту: {self._testMethodName} ---\n")  # Додаємо вивід кінця тесту

    # Тест головної сторінки
    def test_home_page(self):
        print("  Виконуємо GET запит до '/'")
        response = self.app.get('/')
        print(f"  Статус код відповіді: {response.status_code}")
        self.assertEqual(response.status_code, 200)
        print("  Перевіряємо наявність 'FlowerStream' у відповіді.")
        self.assertIn('FlowerStream', response.data.decode('utf-8'))
        print("  Тест головної сторінки успішно завершено.")

    # Тест входу адміністратора (успішний)
    def test_admin_login_success(self):
        print("  Виконуємо POST запит до '/admin/login' з коректними даними.")
        with self.app as client:
            response = client.post('/admin/login', data=dict(
                username='admin',
                password='admin123'
            ), follow_redirects=True)
            print(f"  Статус код відповіді: {response.status_code}")
            self.assertEqual(response.status_code, 200)

            flashed_messages = [str(m) for m in get_flashed_messages()]
            print(f"  Отримані Flash-повідомлення: {flashed_messages}")
            print("  Перевіряємо наявність 'Успішний вхід!' у Flash-повідомленнях.")
            self.assertIn('Успішний вхід!', flashed_messages)

            with client.session_transaction() as sess:
                print(f"  Перевіряємо стан сесії: admin_logged_in = {sess.get('admin_logged_in')}")
                self.assertTrue(sess.get('admin_logged_in'))
            print("  Тест успішного входу адміністратора завершено.")

    # Тест входу адміністратора (невдалий)
    def test_admin_login_failure(self):
        print("  Виконуємо POST запит до '/admin/login' з некоректними даними.")
        with self.app as client:
            response = client.post('/admin/login', data=dict(
                username='wrong_admin',
                password='wrong_password'
            ), follow_redirects=True)
            print(f"  Статус код відповіді: {response.status_code}")
            self.assertEqual(response.status_code, 200)

            flashed_messages = [str(m) for m in get_flashed_messages()]
            print(f"  Отримані Flash-повідомлення: {flashed_messages}")
            print("  Перевіряємо наявність 'Невірні дані' у Flash-повідомленнях.")
            self.assertIn('Невірні дані', flashed_messages)

            with client.session_transaction() as sess:
                print(f"  Перевіряємо стан сесії: admin_logged_in = {sess.get('admin_logged_in')}")
                self.assertFalse(sess.get('admin_logged_in'))
            print("  Тест невдалого входу адміністратора завершено.")

    # Тест виходу адміністратора
    def test_admin_logout(self):
        print("  Спочатку входимо як адмін для підготовки тесту.")
        with self.app as client:
            with client.session_transaction() as sess:
                sess['admin_logged_in'] = True
            print("  Виконуємо GET запит до '/admin/logout'.")
            response = client.get('/admin/logout', follow_redirects=True)
            print(f"  Статус код відповіді: {response.status_code}")
            self.assertEqual(response.status_code, 200)

            flashed_messages = [str(m) for m in get_flashed_messages()]
            print(f"  Отримані Flash-повідомлення: {flashed_messages}")
            print("  Перевіряємо наявність 'Ви вийшли з системи.' у Flash-повідомленнях.")
            self.assertIn('Ви вийшли з системи.', flashed_messages)

            with client.session_transaction() as sess:
                print(f"  Перевіряємо стан сесії: admin_logged_in = {sess.get('admin_logged_in')}")
                self.assertFalse(sess.get('admin_logged_in'))
            print("  Тест виходу адміністратора завершено.")

    # Тест додавання товару в кошик
    def test_add_to_cart(self):
        flower_id = flowers[0]['id']
        print(f"  Додаємо товар з ID {flower_id} до кошика.")
        with self.app as client:
            response = client.post(f'/add_to_cart/{flower_id}', follow_redirects=True)
            print(f"  Статус код відповіді: {response.status_code}")
            self.assertEqual(response.status_code, 200)

            flashed_messages = [str(m) for m in get_flashed_messages()]
            print(f"  Отримані Flash-повідомлення: {flashed_messages}")
            self.assertIn(f"{flowers[0]['name']} додано до кошика.", flashed_messages)

            with client.session_transaction() as sess:
                cart = sess.get('cart')
                print(f"  Вміст кошика у сесії: {cart}")
                self.assertIsNotNone(cart)
                self.assertEqual(len(cart), 1)
                self.assertEqual(cart[0]['id'], flower_id)
                self.assertEqual(cart[0]['quantity'], 1)
            print("  Тест додавання товару в кошик завершено.")

    # Тест додавання того ж товару в кошик (збільшення кількості)
    def test_add_same_item_to_cart_increases_quantity(self):
        flower_id = flowers[0]['id']
        with self.app as client:
            print(f"  Додаємо товар з ID {flower_id} перший раз.")
            client.post(f'/add_to_cart/{flower_id}')
            print(f"  Додаємо товар з ID {flower_id} другий раз.")
            response = client.post(f'/add_to_cart/{flower_id}', follow_redirects=True)
            print(f"  Статус код відповіді: {response.status_code}")
            self.assertEqual(response.status_code, 200)

            flashed_messages = [str(m) for m in get_flashed_messages()]
            print(f"  Отримані Flash-повідомлення: {flashed_messages}")
            self.assertIn(f"{flowers[0]['name']} додано до кошика.", flashed_messages)

            with client.session_transaction() as sess:
                cart = sess.get('cart')
                print(f"  Вміст кошика у сесії: {cart}")
                self.assertIsNotNone(cart)
                self.assertEqual(len(cart), 1)
                self.assertEqual(cart[0]['id'], flower_id)
                self.assertEqual(cart[0]['quantity'], 2)
            print("  Тест збільшення кількості товару в кошику завершено.")

    # Тест видалення товару з кошика
    def test_remove_from_cart(self):
        with self.app as client:
            flower_id = flowers[0]['id']
            print(f"  Додаємо товар з ID {flower_id} до кошика для підготовки.")
            client.post(f'/add_to_cart/{flower_id}')
            with client.session_transaction() as sess:
                print(f"  Кошик до видалення: {sess.get('cart', [])}")
                self.assertEqual(len(sess.get('cart', [])), 1)

            print("  Виконуємо POST запит для видалення першого елемента з кошика.")
            response = client.post('/remove_from_cart/0', follow_redirects=True)
            print(f"  Статус код відповіді: {response.status_code}")
            self.assertEqual(response.status_code, 200)

            flashed_messages = [str(m) for m in get_flashed_messages()]
            print(f"  Отримані Flash-повідомлення: {flashed_messages}")
            self.assertIn(f"{flowers[0]['name']} видалено з кошика.", flashed_messages)

            with client.session_transaction() as sess:
                print(f"  Кошик після видалення: {sess.get('cart', [])}")
                self.assertEqual(len(sess.get('cart', [])), 0)
            print("  Тест видалення товару з кошика завершено.")

    # Тест збільшення кількості товару в кошику
    def test_increase_quantity(self):
        with self.app as client:
            flower_id = flowers[0]['id']
            print(f"  Додаємо товар з ID {flower_id} до кошика.")
            client.post(f'/add_to_cart/{flower_id}')
            with client.session_transaction() as sess:
                print(f"  Початкова кількість товару: {sess['cart'][0]['quantity']}")
                self.assertEqual(sess['cart'][0]['quantity'], 1)

            print("  Виконуємо POST запит для збільшення кількості.")
            response = client.post('/increase_quantity/0', follow_redirects=True)
            print(f"  Статус код відповіді: {response.status_code}")
            self.assertEqual(response.status_code, 200)
            with client.session_transaction() as sess:
                print(f"  Кількість товару після збільшення: {sess['cart'][0]['quantity']}")
                self.assertEqual(sess['cart'][0]['quantity'], 2)
            print("  Тест збільшення кількості товару завершено.")

    # Тест зменшення кількості товару в кошику
    def test_decrease_quantity(self):
        with self.app as client:
            flower_id = flowers[0]['id']
            print(f"  Додаємо товар з ID {flower_id} двічі для початкової кількості 2.")
            client.post(f'/add_to_cart/{flower_id}')
            client.post(f'/add_to_cart/{flower_id}')
            with client.session_transaction() as sess:
                print(f"  Початкова кількість товару: {sess['cart'][0]['quantity']}")
                self.assertEqual(sess['cart'][0]['quantity'], 2)

            print("  Виконуємо POST запит для зменшення кількості.")
            response = client.post('/decrease_quantity/0', follow_redirects=True)
            print(f"  Статус код відповіді: {response.status_code}")
            self.assertEqual(response.status_code, 200)
            with client.session_transaction() as sess:
                print(f"  Кількість товару після зменшення: {sess['cart'][0]['quantity']}")
                self.assertEqual(sess['cart'][0]['quantity'], 1)
            print("  Тест зменшення кількості товару завершено.")

    # Тест зменшення кількості товару до 0 (не має зменшитись нижче 1)
    def test_decrease_quantity_to_zero(self):
        with self.app as client:
            flower_id = flowers[0]['id']
            print(f"  Додаємо товар з ID {flower_id} для початкової кількості 1.")
            client.post(f'/add_to_cart/{flower_id}')
            with client.session_transaction() as sess:
                print(f"  Початкова кількість товару: {sess['cart'][0]['quantity']}")
                self.assertEqual(sess['cart'][0]['quantity'], 1)

            print("  Виконуємо POST запит для зменшення кількості (має залишитися 1).")
            response = client.post('/decrease_quantity/0', follow_redirects=True)
            print(f"  Статус код відповіді: {response.status_code}")
            self.assertEqual(response.status_code, 200)
            with client.session_transaction() as sess:
                print(f"  Кількість товару після спроби зменшення: {sess['cart'][0]['quantity']}")
                self.assertEqual(sess['cart'][0]['quantity'], 1)
            print("  Тест зменшення кількості товару до 0 завершено.")

    # Тест перегляду кошика
    def test_view_cart(self):
        print("  Виконуємо GET запит до '/cart'.")
        response = self.app.get('/cart')
        print(f"  Статус код відповіді: {response.status_code}")
        self.assertEqual(response.status_code, 200)
        print("  Перевіряємо наявність 'Ваш кошик' у відповіді.")
        self.assertIn('Ваш кошик', response.data.decode('utf-8'))
        print("  Перевіряємо наявність 'Кошик порожній.' у відповіді.")
        self.assertIn('Кошик порожній.', response.data.decode('utf-8'))
        print("  Тест перегляду кошика завершено.")

    # Тест оформлення замовлення (успішний)
    def test_checkout_success(self):
        with self.app as client:
            flower_id = flowers[0]["id"]
            print(f"  Додаємо товар з ID {flower_id} до кошика для підготовки оформлення замовлення.")
            client.post(f'/add_to_cart/{flower_id}')
            print("  Виконуємо POST запит до '/checkout' з коректними даними.")
            response = client.post('/checkout', data=dict(
                full_name='Test User',
                address='Київ, Україна',
                notes='Додаткові нотатки',
                agree='yes'
            ), follow_redirects=True)
            print(f"  Статус код відповіді: {response.status_code}")
            self.assertEqual(response.status_code, 200)

            flashed_messages = [str(m) for m in get_flashed_messages()]
            print(f"  Отримані Flash-повідомлення: {flashed_messages}")
            self.assertIn('Замовлення оформлено! Дякуємо!', flashed_messages)

            with client.session_transaction() as sess:
                print(f"  Перевіряємо стан кошика у сесії після оформлення: {sess.get('cart')}")
                self.assertIsNone(sess.get('cart'))
            print("  Тест успішного оформлення замовлення завершено.")

    # Тест оформлення замовлення (невдалий - відсутні поля)
    def test_checkout_missing_fields(self):
        with self.app as client:
            flower_id = flowers[0]["id"]
            print(f"  Додаємо товар з ID {flower_id} до кошика для підготовки оформлення замовлення.")
            client.post(f'/add_to_cart/{flower_id}')
            print("  Виконуємо POST запит до '/checkout' з відсутніми даними.")
            response = client.post('/checkout', data=dict(
                full_name='',
                address='Київ, Україна',
                notes='Додаткові нотатки',
                agree='yes'
            ), follow_redirects=True)
            print(f"  Статус код відповіді: {response.status_code}")
            self.assertEqual(response.status_code, 200)

            flashed_messages = [str(m) for m in get_flashed_messages()]
            print(f"  Отримані Flash-повідомлення: {flashed_messages}")
            self.assertIn("Заповніть обов'язкові поля та погодьтесь з умовами.", flashed_messages)

            with client.session_transaction() as sess:
                print(f"  Перевіряємо стан кошика у сесії: {sess.get('cart')}")
                self.assertIsNotNone(sess.get('cart'))
            print("  Тест невдалого оформлення замовлення завершено.")

    # Тест реєстрації (успішний)
    def test_register_success(self):
        with self.app as client:
            print("  Виконуємо POST запит до '/register' з коректними даними.")
            response = client.post('/register', data=dict(
                username='newuser',
                password='newpassword',
                confirm='newpassword'
            ), follow_redirects=True)
            print(f"  Статус код відповіді: {response.status_code}")
            self.assertEqual(response.status_code, 200)

            flashed_messages = [str(m) for m in get_flashed_messages()]
            print(f"  Отримані Flash-повідомлення: {flashed_messages}")
            self.assertIn('Реєстрація успішна! Тепер увійдіть.', flashed_messages)

            print("  Перевіряємо перенаправлення на 'Вхід адміністратора'.")
            self.assertIn('Вхід адміністратора', response.data.decode('utf-8'))
            print("  Тест успішної реєстрації завершено.")

    # Тест реєстрації (паролі не збігаються)
    def test_register_password_mismatch(self):
        with self.app as client:
            print("  Виконуємо POST запит до '/register' з незбіжними паролями.")
            response = client.post('/register', data=dict(
                username='testuser',
                password='password1',
                confirm='password2'
            ), follow_redirects=True)
            print(f"  Статус код відповіді: {response.status_code}")
            self.assertEqual(response.status_code, 200)

            flashed_messages = [str(m) for m in get_flashed_messages()]
            print(f"  Отримані Flash-повідомлення: {flashed_messages}")
            self.assertIn('Паролі не збігаються.', flashed_messages)
            print("  Тест реєстрації з незбіжними паролями завершено.")

    # Тест реєстрації (відсутні поля)
    def test_register_missing_fields(self):
        with self.app as client:
            print("  Виконуємо POST запит до '/register' з відсутніми полями.")
            response = client.post('/register', data=dict(
                username='testuser',
                password='password',
                confirm=''
            ), follow_redirects=True)
            print(f"  Статус код відповіді: {response.status_code}")
            self.assertEqual(response.status_code, 200)

            flashed_messages = [str(m) for m in get_flashed_messages()]
            print(f"  Отримані Flash-повідомлення: {flashed_messages}")
            self.assertIn('Будь ласка, заповніть усі поля.', flashed_messages)
            print("  Тест реєстрації з відсутніми полями завершено.")

    # Тест додавання товару до обраного
    def test_add_to_favorites(self):
        flower_id = flowers[0]['id']
        print(f"  Додаємо товар з ID {flower_id} до обраного.")
        with self.app as client:
            response = client.post(f'/add_to_favorites/{flower_id}', follow_redirects=True)
            print(f"  Статус код відповіді: {response.status_code}")
            self.assertEqual(response.status_code, 200)

            flashed_messages = [str(m) for m in get_flashed_messages()]
            print(f"  Отримані Flash-повідомлення: {flashed_messages}")
            self.assertIn(f"{flowers[0]['name']} додано в обране.", flashed_messages)

            with client.session_transaction() as sess:
                favorites = sess.get('favorites')
                print(f"  Вміст обраного у сесії: {favorites}")
                self.assertIsNotNone(favorites)
                self.assertEqual(len(favorites), 1)
                self.assertEqual(favorites[0]['id'], flower_id)
            print("  Тест додавання товару до обраного завершено.")

    # Тест додавання того ж товару до обраного (вже є)
    def test_add_same_item_to_favorites_already_exists(self):
        flower_id = flowers[0]['id']
        with self.app as client:
            print(f"  Додаємо товар з ID {flower_id} до обраного (перший раз).")
            client.post(f'/add_to_favorites/{flower_id}')
            print(f"  Спроба додати той самий товар з ID {flower_id} до обраного (вдруге).")
            response = client.post(f'/add_to_favorites/{flower_id}', follow_redirects=True)
            print(f"  Статус код відповіді: {response.status_code}")
            self.assertEqual(response.status_code, 200)

            flashed_messages = [str(m) for m in get_flashed_messages()]
            print(f"  Отримані Flash-повідомлення: {flashed_messages}")
            self.assertIn('Ця квітка вже в обраному.', flashed_messages)

            with client.session_transaction() as sess:
                favorites = sess.get('favorites')
                print(f"  Вміст обраного у сесії: {favorites}")
                self.assertEqual(len(favorites), 1)
            print("  Тест додавання того ж товару до обраного завершено.")

    # Тест видалення товару з обраного
    def test_remove_from_favorites(self):
        with self.app as client:
            flower_id = flowers[0]['id']
            print(f"  Додаємо товар з ID {flower_id} до обраного для підготовки.")
            client.post(f'/add_to_favorites/{flower_id}')
            with client.session_transaction() as sess:
                print(f"  Обране до видалення: {sess.get('favorites', [])}")
                self.assertEqual(len(sess.get('favorites', [])), 1)

            print(f"  Виконуємо POST запит для видалення товару з ID {flower_id} з обраного.")
            response = client.post(f'/remove_from_favorites/{flower_id}', follow_redirects=True)
            print(f"  Статус код відповіді: {response.status_code}")
            self.assertEqual(response.status_code, 200)

            flashed_messages = [str(m) for m in get_flashed_messages()]
            print(f"  Отримані Flash-повідомлення: {flashed_messages}")
            self.assertIn('Товар видалено з обраного.', flashed_messages)

            with client.session_transaction() as sess:
                print(f"  Обране після видалення: {sess.get('favorites', [])}")
                self.assertEqual(len(sess.get('favorites', [])), 0)
            print("  Тест видалення товару з обраного завершено.")

    # Тест перегляду обраного
    def test_view_favorites(self):
        print("  Виконуємо GET запит до '/favorites'.")
        response = self.app.get('/favorites')
        print(f"  Статус код відповіді: {response.status_code}")
        self.assertEqual(response.status_code, 200)
        print("  Перевіряємо наявність 'Улюблені товари' у відповіді.")
        self.assertIn('Улюблені товари', response.data.decode('utf-8'))
        print("  Перевіряємо наявність 'У вас ще немає улюблених товарів.' у відповіді.")
        self.assertIn('У вас ще немає улюблених товарів.', response.data.decode('utf-8'))
        print("  Тест перегляду обраного завершено.")

    # Тест редагування квітки адміністратором
    def test_edit_flower_as_admin(self):
        flower_id = flowers[0]['id']
        with self.app as client:
            print("  Входимо як адмін для можливості редагування.")
            with client.session_transaction() as sess:
                sess['admin_logged_in'] = True

            new_name = 'Нова назва троянди'
            new_description = 'Оновлений опис'
            new_price = 175.50
            print(f"  Виконуємо POST запит до '/edit/{flower_id}' для оновлення квітки.")
            response = client.post(f'/edit/{flower_id}', data=dict(
                name=new_name,
                description=new_description,
                price=new_price
            ), follow_redirects=True)
            print(f"  Статус код відповіді: {response.status_code}")
            self.assertEqual(response.status_code, 200)

            flashed_messages = [str(m) for m in get_flashed_messages()]
            print(f"  Отримані Flash-повідомлення: {flashed_messages}")
            self.assertIn(f"Квітка #{flower_id} оновлена.", flashed_messages)

            updated_flower = next((f for f in flowers if f['id'] == flower_id), None)
            print(f"  Оновлені дані квітки у списку: {updated_flower}")
            self.assertIsNotNone(updated_flower)
            self.assertEqual(updated_flower['name'], new_name)
            self.assertEqual(updated_flower['description'], new_description)
            self.assertEqual(updated_flower['price'], new_price)
            print("  Тест редагування квітки адміністратором завершено.")

    # Тест редагування квітки без входу адміністратора
    def test_edit_flower_without_admin_login(self):
        flower_id = flowers[0]['id']
        print(f"  Спроба редагування квітки з ID {flower_id} без входу адміна.")
        response = self.app.post(f'/edit/{flower_id}', data=dict(
            name='Спроба редагування',
            description='Спроба',
            price=1.0
        ), follow_redirects=True)
        print(f"  Статус код відповіді: {response.status_code}")
        self.assertEqual(response.status_code, 200)
        print("  Перевіряємо перенаправлення на 'Вхід адміністратора'.")
        self.assertIn('Вхід адміністратора', response.data.decode('utf-8'))
        print("  Тест редагування квітки без входу адміністратора завершено.")


if __name__ == '__main__':
    unittest.main()