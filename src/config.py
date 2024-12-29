import os
from dotenv import load_dotenv
from cryptography.fernet import Fernet

# Load environment variables
load_dotenv()

# Knack configuration
KNACK_APP_ID = os.getenv('KNACK_APP_ID')
KNACK_API_KEY = os.getenv('KNACK_API_KEY')

# Financial APIs configuration
PLAID_CLIENT_ID = os.getenv('PLAID_CLIENT_ID')
PLAID_SECRET = os.getenv('PLAID_SECRET')
BOFA_API_KEY = os.getenv('BOFA_API_KEY')
BILLDOTCOM_API_KEY = os.getenv('BILLDOTCOM_API_KEY')
WELLS_FARGO_API_KEY = os.getenv('WELLS_FARGO_API_KEY')

# Bank credentials (encrypted)
ENCRYPTION_KEY = os.getenv('ENCRYPTION_KEY', Fernet.generate_key().decode())
cipher_suite = Fernet(ENCRYPTION_KEY.encode())

def decrypt_value(encrypted_value: str) -> str:
    """Decrypt an encrypted value"""
    if not encrypted_value:
        return ''
    try:
        return cipher_suite.decrypt(encrypted_value.encode()).decode()
    except Exception:
        return encrypted_value

# Bank of America credentials
BOFA_USERNAME = decrypt_value(os.getenv('BOFA_USERNAME', ''))
BOFA_PASSWORD = decrypt_value(os.getenv('BOFA_PASSWORD', ''))
BOFA_ACCOUNT_NUMBER = os.getenv('BOFA_ACCOUNT_NUMBER')  # Last 4 digits is sufficient

# Wells Fargo credentials
WELLS_FARGO_USERNAME = decrypt_value(os.getenv('WELLS_FARGO_USERNAME', ''))
WELLS_FARGO_PASSWORD = decrypt_value(os.getenv('WELLS_FARGO_PASSWORD', ''))
WELLS_FARGO_ACCOUNT_NUMBER = os.getenv('WELLS_FARGO_ACCOUNT_NUMBER')  # Last 4 digits is sufficient

# AWS Configuration
AWS_ACCESS_KEY_ID = os.getenv('AWS_ACCESS_KEY_ID')
AWS_SECRET_ACCESS_KEY = os.getenv('AWS_SECRET_ACCESS_KEY')
AWS_REGION = os.getenv('AWS_REGION', 'us-east-1')

# Application settings
REPORT_OUTPUT_DIR = 'reports'
TRANSACTION_MATCH_THRESHOLD = 0.95  # Confidence threshold for transaction matches

def encrypt_value(value: str) -> str:
    """Encrypt a value for storing in environment variables"""
    return cipher_suite.encrypt(value.encode()).decode()

def load_config():
    """Load and return all configuration values as a dictionary"""
    return {
        'KNACK_APP_ID': KNACK_APP_ID,
        'KNACK_API_KEY': KNACK_API_KEY,
        'PLAID_CLIENT_ID': PLAID_CLIENT_ID,
        'PLAID_SECRET': PLAID_SECRET,
        'BOFA_USERNAME': BOFA_USERNAME,
        'BOFA_PASSWORD': BOFA_PASSWORD,
        'BOFA_ACCOUNT_NUMBER': BOFA_ACCOUNT_NUMBER,
        'WELLS_FARGO_USERNAME': WELLS_FARGO_USERNAME,
        'WELLS_FARGO_PASSWORD': WELLS_FARGO_PASSWORD,
        'WELLS_FARGO_ACCOUNT_NUMBER': WELLS_FARGO_ACCOUNT_NUMBER,
        'AWS_ACCESS_KEY_ID': AWS_ACCESS_KEY_ID,
        'AWS_SECRET_ACCESS_KEY': AWS_SECRET_ACCESS_KEY,
        'AWS_REGION': AWS_REGION,
        'ENCRYPTION_KEY': ENCRYPTION_KEY
    }
