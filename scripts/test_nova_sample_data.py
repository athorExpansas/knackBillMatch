import asyncio
import logging
from pathlib import Path
import sys
import json
import base64
from tkinter import filedialog
import tkinter as tk
import traceback

# Add project root to path
project_root = str(Path(__file__).parent.parent)
sys.path.append(project_root)

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

from src.nova_client import NovaClient

async def get_bank_statement():
    """Get bank statement file path"""
    logger.debug("Creating root window...")
    root = tk.Tk()
    root.withdraw()
    
    logger.debug("Opening file dialog...")
    statement_path = filedialog.askopenfilename(
        title="Select Bank Statement CSV",
        filetypes=[("CSV files", "*.csv")]
    )
    logger.debug(f"Selected statement: {statement_path}")
    
    root.destroy()
    return statement_path

async def main():
    try:
        # Initialize Nova client
        logger.debug("Creating NovaClient...")
        nova = NovaClient()
        await nova.initialize()
        logger.debug("NovaClient initialized")
        
        # Get bank statement
        statement_path = await get_bank_statement()
        if not statement_path:
            logger.error("No bank statement selected")
            return
            
        # Read bank statement
        logger.debug("Reading bank statement...")
        with open(statement_path, 'r') as f:
            csv_content = f.read()
        
        # Create simple request
        request = {
            "messages": [
                {
                    "role": "user",
                    "content": [{"text": csv_content}]
                },
                {
                    "role": "assistant",
                    "content": [{"text": "I'll help analyze the bank statement."}]
                },
                {
                    "role": "user",
                    "content": [{"text": "What is the total amount of payments made to The Mapleton Andover LLC?"}]
                }
            ]
        }
        
        # Send request
        logger.debug("Sending request to Nova...")
        try:
            # Make synchronous call
            response = nova.runtime.invoke_model(
                modelId="arn:aws:bedrock:us-west-2:664604937404:inference-profile/us.amazon.nova-pro-v1:0",
                contentType="application/json",
                accept="application/json",
                body=json.dumps(request)
            )
            
            if response and hasattr(response, 'get'):
                response_body = json.loads(response.get('body').read())
                print("Nova Response:", response_body)
            else:
                print("No response from Nova")

        except Exception as e:
            logger.error(f"Error: {str(e)}")
            traceback.print_exc()
        
    except Exception as e:
        logger.error(f"Error: {e}")
        raise

if __name__ == "__main__":
    asyncio.run(main())
