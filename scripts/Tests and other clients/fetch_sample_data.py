import sys
import os
from datetime import datetime, timedelta
import json
from pathlib import Path
import asyncio

# Add the project root directory to the Python path
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

from src.financial_clients import BankOfAmericaClient, WellsFargoClient
from src.knack_client import KnackClient
from src.config import load_config

def save_to_json(data, filename):
    """Save data to a JSON file in the samples directory."""
    samples_dir = Path(__file__).parent.parent / 'samples'
    samples_dir.mkdir(exist_ok=True)
    
    filepath = samples_dir / filename
    with open(filepath, 'w') as f:
        json.dump(data, f, indent=2, default=str)
    print(f"Saved sample data to {filepath}")

async def main():
    # Load configuration
    config = load_config()
    
    # Use the last 30 days for testing
    end_date = datetime.now()
    start_date = end_date - timedelta(days=30)
    
    print(f"Fetching transactions from {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")
    
    try:
        # Fetch Bank of America transactions
        bofa_client = BankOfAmericaClient()
        bofa_transactions = await bofa_client.get_transactions(start_date, end_date)
        save_to_json(bofa_transactions, 'bofa_samples.json')
        
        # Fetch Wells Fargo transactions
        wf_client = WellsFargoClient()
        wf_transactions = await wf_client.get_transactions(start_date, end_date)
        save_to_json(wf_transactions, 'wellsfargo_samples.json')
        
        # Fetch Knack records
        knack_client = KnackClient(config['KNACK_APP_ID'], config['KNACK_API_KEY'])
        knack_records = await knack_client.get_records()
        save_to_json(knack_records, 'knack_samples.json')
        
        # Knack - Get unbilled records
        try:
            unbilled_records = await knack_client.get_unbilled_records()
            print(f"Found {len(unbilled_records)} unbilled records")
            
            # Save to file
            with open('samples/knack_unbilled.json', 'w') as f:
                json.dump(unbilled_records, f, indent=2)
            print(f"Saved unbilled records to {f.name}")
            
            # Print first record as sample
            if unbilled_records:
                print("\nSample unbilled record:")
                print(json.dumps(unbilled_records[0], indent=2))
        except Exception as e:
            print(f"Error getting Knack unbilled records: {str(e)}")
        
    except Exception as e:
        print(f"Error fetching sample data: {str(e)}")
        raise

if __name__ == "__main__":
    asyncio.run(main())
