import aiohttp
import asyncio
from typing import List, Dict, Optional
from datetime import datetime
import logging
import json
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)

class KnackClient:
    def __init__(self):
        self.app_id = os.getenv('KNACK_APP_ID')
        self.api_key = os.getenv('KNACK_API_KEY')
        
        if not all([self.app_id, self.api_key]):
            raise ValueError("Missing required Knack credentials in environment variables")
        
        self.base_url = f"https://api.knack.com/v1/objects/object_108/records"
        self.headers = {
            "X-Knack-Application-Id": self.app_id,
            "X-Knack-REST-API-Key": self.api_key,
            "Content-Type": "application/json"
        }
    
    async def get_records(self, start_date: Optional[datetime] = None, end_date: Optional[datetime] = None) -> List[Dict]:
        """
        Get all records from Knack database with optional date filtering
        Args:
            start_date: Optional start date for filtering records
            end_date: Optional end date for filtering records
        Returns:
            List of records
        """
        async with aiohttp.ClientSession() as session:
            filters = {}
            if start_date and end_date:
                filters = {
                    "match": "and",
                    "rules": [
                        {
                            "field": "field_123",  # Date field
                            "operator": "is during",
                            "value": {
                                "from": start_date.strftime("%Y-%m-%d"),
                                "to": end_date.strftime("%Y-%m-%d")
                            }
                        }
                    ]
                }
            
            all_records = []
            page = 1
            rows_per_page = 25
            
            while True:
                params = {
                    "page": page,
                    "rows_per_page": rows_per_page
                }
                if filters:
                    params["filters"] = json.dumps(filters)
                
                async with session.get(self.base_url, headers=self.headers, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        records = data.get("records", [])
                        all_records.extend(records)
                        
                        # Check if we've received all records
                        total_records = data.get("total_records", 0)
                        current_count = len(all_records)
                        
                        logger.info(f"Retrieved {len(records)} records from page {page} (Total: {current_count}/{total_records})")
                        
                        if current_count >= total_records:
                            break
                        
                        page += 1
                    else:
                        error_text = await response.text()
                        logger.error(f"Failed to fetch Knack records: {response.status} - {error_text}")
                        raise Exception(f"Failed to fetch Knack records: {response.status} - {error_text}")
            
            return all_records
    
    async def get_unbilled_records(self) -> List[Dict]:
        """
        Get unbilled records from Knack database
        These are records where:
        - field_2386 is No
        - field_1751 is No
        
        Note: Knack uses "Yes"/"No" strings for boolean fields
        Returns:
            List of unbilled records
        """
        async with aiohttp.ClientSession() as session:
            filters = {
                "match": "and",
                "rules": [
                    {
                        "field": "field_2386",
                        "operator": "is",
                        "value": "No"
                    },
                    {
                        "field": "field_1751",
                        "operator": "is",
                        "value": "No"
                    }
                ]
            }
            
            all_records = []
            page = 1
            rows_per_page = 25
            
            while True:
                params = {
                    "page": page,
                    "rows_per_page": rows_per_page,
                    "filters": json.dumps(filters)
                }
                
                async with session.get(self.base_url, headers=self.headers, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        records = data.get("records", [])
                        all_records.extend(records)
                        
                        # Check if we've received all records
                        total_records = data.get("total_records", 0)
                        current_count = len(all_records)
                        
                        logger.info(f"Retrieved {len(records)} unbilled records from page {page} (Total: {current_count}/{total_records})")
                        
                        if current_count >= total_records:
                            break
                        
                        page += 1
                    else:
                        error_text = await response.text()
                        logger.error(f"Failed to fetch unbilled records: {response.status} - {error_text}")
                        raise Exception(f"Failed to fetch unbilled records: {response.status} - {error_text}")
            
            return all_records

    async def get_unpaid_approved_billings(self) -> List[Dict]:
        """
        Get unpaid, approved billings that aren't deleted, written off, or already matched
        Filters:
        - field_1440 (Billing Approved) = Yes
        - field_2389 (Paid in full) = No
        - field_2968 (Write Off Amount) = No
        - field_1751 (Delete Billing) = No
        - field_2379 (Matched) = No
        
        Note: Knack uses "Yes"/"No" strings for boolean fields
        Returns:
            List of billing records
        """
        async with aiohttp.ClientSession() as session:
            filters = {
                "match": "and",
                "rules": [
                    {
                        "field": "field_1440",
                        "operator": "is",
                        "value": "Yes"
                    },
                    {
                        "field": "field_2389",
                        "operator": "is",
                        "value": "No"
                    },
                    {
                        "field": "field_2968",
                        "operator": "is",
                        "value": "No"
                    },
                    {
                        "field": "field_1751",
                        "operator": "is",
                        "value": "No"
                    },
                    {
                        "field": "field_2379",
                        "operator": "is",
                        "value": "No"
                    }
                ]
            }
            
            all_records = []
            page = 1
            rows_per_page = 25
            
            while True:
                params = {
                    "page": page,
                    "rows_per_page": rows_per_page,
                    "filters": json.dumps(filters)
                }
                
                async with session.get(self.base_url, headers=self.headers, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        records = data.get("records", [])
                        all_records.extend(records)
                        
                        # Check if we've received all records
                        total_records = data.get("total_records", 0)
                        current_count = len(all_records)
                        
                        logger.info(f"Retrieved {len(records)} unpaid approved billings from page {page} (Total: {current_count}/{total_records})")
                        
                        if current_count >= total_records:
                            break
                        
                        page += 1
                    else:
                        error_text = await response.text()
                        logger.error(f"Failed to fetch unpaid approved billings: {response.status} - {error_text}")
                        raise Exception(f"Failed to fetch unpaid approved billings: {response.status} - {error_text}")
            
            return all_records
    
    async def update_record_status(self, record_id: str, payment_info: Dict):
        """
        Update a Knack record with payment information
        Args:
            record_id: The Knack record ID to update
            payment_info: Dictionary containing payment details
        """
        try:
            # For testing, just print the update
            print(f"Would update record {record_id} with {payment_info}")
            
            # TODO: Implement actual API call when ready
            """
            async with aiohttp.ClientSession() as session:
                url = f"{self.base_url}/{record_id}"
                payload = {
                    "field_123": payment_info.get("status"),
                    "field_124": payment_info.get("date"),
                    "field_125": payment_info.get("amount"),
                    "field_126": payment_info.get("reference")
                }
                
                async with session.put(url, headers=self.headers, json=payload) as response:
                    if response.status != 200:
                        print(f"Error updating Knack record: {response.status}")
            """
        except Exception as e:
            print(f"Error updating Knack record: {str(e)}")
