import os

class Config:
    SECRET_KEY = os.getenv('SECRET_KEY')
    DATABASE = os.getenv('DATABASE')
    STRIPE_SECRET_KEY = os.getenv('STRIPE_SECRET_KEY')
    STRIPE_PUBLISHABLE_KEY = os.getenv('STRIPE_PUBLISHABLE_KEY')