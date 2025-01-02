"""Test script for check matching logic."""
import asyncio
import json
import logging
import os
import sys
from pathlib import Path

# Add the project root to Python path
project_root = str(Path(__file__).parent.parent)
sys.path.append(project_root)

from src.llama_client import LlamaClient

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Test data
TEST_CHECK_DATA = [
    {
        "check_number": "3576",
        "amount": "$5,490.00",
        "date": "10/02/2024",
        "payee": "The Mapleton Andover",
        "from": "Dwight Shinkle or Jeff Shinkle",
        "from_address": "FARM ACCOUNT",
        "memo": "",
        "bank_name": "Bank of America"
    },
    {
        "check_number": "5856",
        "amount": "$5,490.00",
        "date": "10/02/2024",
        "payee": "The Mapleton",
        "from": "Kurt A Elliott and Penny K Elliott",
        "from_address": "307 Village Rd, Andover KS 67002-4678",
        "memo": "",
        "bank_name": "Bank of America"
    }
]

TEST_INVOICE_DATA = [
    {
        "invoice_number": "Andover1002831",
        "amount": 5490.0,
        "date": "11/01/2024",
        "payee": "Dwight Shinkle 406",
        "resident_name": "Dwight Shinkle"
    },
    {
        "invoice_number": "Andover1002766",
        "amount": 5000.0,
        "date": "08/01/2024", 
        "payee": "Judith Spencer 6",
        "resident_name": "Judith Spencer"
    }
]

async def test_matching():
    """Test the check matching logic."""
    try:
        llama = LlamaClient()
        
        # Prepare the matching prompt
        prompt = """You are a JSON-only API that matches checks with invoices. Return ONLY a JSON object, no other text.

Rules for matching:
1. Amount Rule: Check amount must match invoice amount exactly or be within $10
2. Name Rule: Check "from" name must match invoice payee name (ignoring unit numbers)
3. Date Rule: Check date should be near invoice date

Example match:
Check: "Dwight Shinkle" for $5,490.00 dated 10/02/2024
Invoice: "Dwight Shinkle 406" for $5,490.00 dated 11/01/2024
Result: MATCH (amount exact, names match, dates close)

Input Data:
{check_data}
{invoice_data}

Return this exact JSON structure (no other text):
{{
    "matches": [
        {{
            "check": {{
                "check_number": "3576",
                "amount": "$5,490.00",
                "date": "10/02/2024",
                "payee": "The Mapleton",
                "from": "Dwight Shinkle or Jeff Shinkle"
            }},
            "invoices": [
                {{
                    "invoice_number": "Andover1002831",
                    "amount": 5490.0,
                    "date": "11/01/2024",
                    "payee": "Dwight Shinkle 406"
                }}
            ],
            "confidence": 0.95,
            "reasoning": "Amount matches exactly ($5,490), dates are close (Oct vs Nov), and from name matches payee (Dwight Shinkle)"
        }}
    ],
    "unmatched_checks": [],
    "unmatched_invoices": []
}}"""

        # Format the prompt with test data
        formatted_prompt = prompt.format(
            check_data=json.dumps(TEST_CHECK_DATA, indent=2),
            invoice_data=json.dumps(TEST_INVOICE_DATA, indent=2)
        )

        # Get response from Llama
        text_response = await llama.process_text(formatted_prompt)
        logger.info(f"Raw response:\n{text_response}")

        # Extract JSON from response
        json_start = text_response.find('{')
        json_end = text_response.rfind('}') + 1
        if json_start >= 0 and json_end > json_start:
            json_str = text_response[json_start:json_end]
            try:
                matches = json.loads(json_str)
                logger.info(f"\nMatches found: {len(matches.get('matches', []))}")
                logger.info(f"Unmatched checks: {len(matches.get('unmatched_checks', []))}")
                logger.info(f"Unmatched invoices: {len(matches.get('unmatched_invoices', []))}")
                return matches
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse JSON: {str(e)}\nJSON string: {json_str}")
                return {}
        else:
            logger.error("No JSON found in response")
            return {}

    except Exception as e:
        logger.error(f"Error in test_matching: {str(e)}")
        return {}

if __name__ == "__main__":
    asyncio.run(test_matching())
