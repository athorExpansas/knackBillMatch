import asyncio
import json
from datetime import datetime
import os
from pathlib import Path
import sys
from dotenv import load_dotenv

# Add the project root directory to the Python path
project_root = str(Path(__file__).parent.parent)
sys.path.append(project_root)

from src.knack_client import KnackClient

# Load environment variables
load_dotenv()

async def main():
    try:
        # Initialize Knack client
        knack_client = KnackClient()
        
        # Create a new folder in Downloads for this run
        downloads_path = os.path.join(os.path.expanduser("~"), "Downloads")
        current_date = datetime.now().strftime("%Y%m%d")
        folder_name = f"payment_matching_{current_date}"
        folder_path = os.path.join(downloads_path, folder_name)
        
        # Create the folder if it doesn't exist
        os.makedirs(folder_path, exist_ok=True)
        
        # Get unpaid approved billings
        print("Fetching unpaid approved billings...")
        billings = await knack_client.get_unpaid_approved_billings()
        
        # Create filename
        filename = f"billing_download_{current_date}.json"
        filepath = os.path.join(folder_path, filename)
        
        # Save to the new folder
        with open(filepath, 'w') as f:
            json.dump(billings, f, indent=2)
        
        print(f"Successfully downloaded {len(billings)} billings to {filepath}")
        print(f"\nCreated folder for payment matching: {folder_path}")
        print("You can now add your check PDFs and bank statement to this folder.")
        
        # Print first record as sample if available
        if billings:
            print("\nSample record:")
            print(json.dumps(billings[0], indent=2))
        
    except Exception as e:
        print(f"Error downloading billings: {str(e)}")

if __name__ == "__main__":
    asyncio.run(main())
