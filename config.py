"""Configuration for JASS."""
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
    SQLALCHEMY_DATABASE_URI = f'sqlite:///{os.path.join(BASE_DIR, "jass.db")}'
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Data directory for generated files
    DATA_DIR = os.path.join(BASE_DIR, 'data')
    APPLICATIONS_DIR = os.path.join(DATA_DIR, 'applications')

    # Default AI settings
    DEFAULT_AI_PROVIDER = 'claude'
    DEFAULT_AI_MODEL = 'claude-sonnet-4-20250514'

    # Greenhouse settings
    GREENHOUSE_API_BASE = 'https://boards-api.greenhouse.io/v1/boards'

    # Popular company board tokens for searching
    DEFAULT_BOARDS = [
        'sentinellabs',
        'paloaltonetworks',
        'zscaler',
        'cloudflare',
        'crowdstrike',
        'tanium',
        'rapid7',
        'snyk',
        'unity3d',
        'roblox',
        'rivian',
    ]
