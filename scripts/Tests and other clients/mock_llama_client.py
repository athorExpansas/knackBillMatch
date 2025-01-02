import logging
from typing import Dict, Union
import random
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class MockLlamaClient:
    """Mock Llama client for testing."""
    
    def __init__(self, api_key: str = None, api_url: str = None):
        """Initialize mock client."""
        pass
        
    async def extract_check_info(self, image_data: Union[str, bytes]) -> Dict:
        """Return mock check data for testing."""
        # Generate a random check number
        check_number = str(random.randint(1000, 9999))
        
        # Generate a random amount between $1000 and $10000
        amount = random.uniform(1000, 10000)
        
        # Generate a date within the last 30 days
        date = datetime.now() - timedelta(days=random.randint(0, 30))
        
        # List of mock names
        names = [
            "John Smith",
            "Jane Doe",
            "Robert Johnson",
            "Mary Williams",
            "Michael Brown",
            "The Mapleton",
            "Kurt A Elliott & Penny K Elliot"
        ]
        
        return {
            "check_number": check_number,
            "amount": f"${amount:,.2f}",
            "date": date.strftime("%m/%d/%Y"),
            "payee": random.choice(names),
            "from": random.choice(names),
            "from_address": "123 Main St, Anytown, USA",
            "memo": "Payment for services",
            "bank_name": "First National Bank"
        }
