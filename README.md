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
- **SQLite** 


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

3. Налаштування змінних оточення

```
FLASK_APP=main.py
FLASK_ENV=development
SECRET_KEY=ваш_секретний_ключ
DATABASE_URL=postgresql://username:password@localhost:5432/your_database_name
```

4. Налаштування PostgreSQL

```
sudo -u postgres psql

CREATE USER username WITH PASSWORD 'password';
CREATE DATABASE your_database_name OWNER username;
GRANT ALL PRIVILEGES ON DATABASE your_database_name TO username;
\q
```

5. Запуск проєкту

```
flask run
```

Відкрийте в браузері http://127.0.0.1:5000
