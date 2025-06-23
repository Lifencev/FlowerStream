# Інтернет-магазин квітів FlowerStream

  

**FlowerStream** — веб-магазин для купівлі квітів онлайн, з можливістю перегляду каталогу, авторизації, додавання товарів у кошик або обране, оформлення замовлень та онлайн-оплати.

  

## Розробники:

- Ліфєнцєв
- Моргун
- Стасько

  

## Технології

-  **Back-end/Front-end**: Python: FlaskAPI + jinja2
-  **Database**: SQLite
-  **Auth**: JSON Web Token
-  **Payment**: Stripe


## Структура

```

FlowerStream/

├── app/

│ ├── static/

│ ├── templates/

│ └── app.py

├── tests/

├── .gitignore

├── Pipfile

├── Pipfile.lock

└── README.md

```

## Передумови
- **Git** 
- **Python** (версія 3.8 або новіша)  
- **pipenv** (для ізольованого віртуального середовища)  
- **SQLite** (sqlite3)


##  Налаштування

  

1. Клонування репозиторію:

```
git clone https://github.com/Lifencev/FlowerStream
cd FlowerStream
```

2. Встановлення залежностей через Pipenv:

```
pipenv install
pipenv shell
```

3. Налаштування змінних оточення.
3. Налаштування змінних оточення.
Переіменуйте .env.example на .env та вставте ключі
```
STRIPE_SECRET_KEY=sk_live
STRIPE_PUBLISHABLE_KEY=pk_live
```


4. Запуск проєкту

```
python -m app.app
python -m app.app
```

Відкрийте в браузері http://127.0.0.1:5000
