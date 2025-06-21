import requests
from flask import current_app


def get_uah_to_eur_rate():
    try:
        response = requests.get("https://bank.gov.ua/NBUStatService/v1/statdirectory/exchange?valcode=EUR&json")
        data = response.json()
        rate = float(data[0]['rate'])
        return rate
    except Exception as e:
        print(f"Не вдалося отримати курс НБУ: {e}")
        return 50.0  # extra price in case of error of getting rate


def allowed_file(filename):
    """
    Checks if the file extension is allowed.
    """
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in current_app.config['ALLOWED_EXTENSIONS']
