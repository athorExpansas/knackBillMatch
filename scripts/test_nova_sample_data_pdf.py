import asyncio
import logging
from pathlib import Path
import sys
import json
import base64
from tkinter import filedialog
import tkinter as tk
import traceback
from pdf2image import convert_from_path
import io
from PIL import Image

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

async def get_check_pdf():
    """Get check PDF file path"""
    logger.debug("Creating root window...")
    root = tk.Tk()
    root.withdraw()
    
    logger.debug("Opening file dialog...")
    check_path = filedialog.askopenfilename(
        title="Select Check PDF",
        filetypes=[("PDF files", "*.pdf")]
    )
    logger.debug(f"Selected check: {check_path}")
    
    root.destroy()
    return check_path

async def main():
    try:
        # Initialize Nova client
        logger.debug("Creating NovaClient...")
        nova = NovaClient()
        await nova.initialize()
        logger.debug("NovaClient initialized")
        
        # Get check PDF
        check_path = await get_check_pdf()
        if not check_path:
            logger.error("No check PDF selected")
            return
            
        # Convert PDF to image
        logger.debug("Converting PDF to image...")
        poppler_path = r"C:\poppler\poppler-24.08.0\Library\bin"
        images = convert_from_path(check_path, poppler_path=poppler_path)
        if not images:
            logger.error("No images extracted from PDF")
            return
            
        # Take first page and convert to bytes
        img_byte_arr = io.BytesIO()
        images[0].save(img_byte_arr, format='PNG')
        img_bytes = base64.b64encode(img_byte_arr.getvalue()).decode('utf-8')
        
        # Create request with image
        system_list = [{
            "text": "You are an expert at analyzing check images. Extract key information accurately and format it clearly. Focus ONLY on the check image itself - completely ignore any bank statements, transaction details, or other information that might appear above or around the check. If any information on the check itself is unclear, hard to read, or if there are discrepancies (like between numerical and written amounts on the check), indicate that additional review is needed."
        }]
        
        message_list = [{
            "role": "user",
            "content": [
                {
                    "image": {
                        "format": "png",
                        "source": {"bytes": img_bytes}
                    }
                },
                {
                    "text": "Please analyze ONLY the check image itself. Completely ignore any bank statements or transaction details that might appear above or around the check.\n\nFrom the check image ONLY, extract:\n1. Payee Name (Pay to the Order of)\n2. Amount (both numerical and written)\n3. Date on the check\n4. Check Number\n5. Drawer/Account Holder Name\n\nAfter listing the extracted information, please add:\n6. Additional Review Required (Yes/No): Indicate if any fields ON THE CHECK ITSELF were unclear, hard to read, or if there are discrepancies between numerical and written amounts ON THE CHECK. If yes, explain why. Do not compare with any transaction details outside the check.\n\nPlease format the response clearly with labels for each piece of information."
                }
            ]
        }]
        
        inference_config = {
            "max_new_tokens": 1000,
            "top_p": 0.9,
            "top_k": 250,
            "temperature": 0.1
        }
        
        request = {
            "schemaVersion": "messages-v1",
            "messages": message_list,
            "system": system_list,
            "inferenceConfig": inference_config
        }
        
        # Send request
        logger.debug("Sending request to Nova...")
        try:
            response = nova.runtime.invoke_model(
                modelId="us.amazon.nova-lite-v1:0",
                body=json.dumps(request)
            )
            
            if response:
                model_response = json.loads(response["body"].read())
                print("Nova Response:", json.dumps(model_response, indent=2))
                
                if 'output' in model_response and 'message' in model_response['output']:
                    print("\nExtracted Information:")
                    print(model_response['output']['message']['content'][0]['text'])
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
