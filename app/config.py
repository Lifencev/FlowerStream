import os
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv())

class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret')
    DATABASE   = os.getenv('DATABASE', 'database.db')
    STRIPE_SECRET_KEY      = os.getenv('STRIPE_SECRET_KEY', '')
    STRIPE_PUBLISHABLE_KEY = os.getenv('STRIPE_PUBLISHABLE_KEY', '')
    UPLOAD_FOLDER  = os.getenv('UPLOAD_FOLDER', 'static/images')
    ALLOWED_EXTENSIONS = set(os.getenv('ALLOWED_EXTENSIONS', 'png,jpg,jpeg,gif').split(','))