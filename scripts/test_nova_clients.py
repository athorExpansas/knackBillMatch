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

from src.nova_client import NovaLiteClient, NovaProClient

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
        # Initialize Nova clients
        logger.debug("Creating Nova clients...")
        nova_lite = NovaLiteClient()
        nova_pro = NovaProClient()
        await nova_lite.initialize()
        await nova_pro.initialize()
        logger.debug("Nova clients initialized")
        
        # Get check PDF
        check_path = await get_check_pdf()
        if not check_path:
            logger.error("No file selected")
            return
            
        # Convert PDF to image
        logger.debug("Converting PDF to image...")
        poppler_path = r"C:\poppler\poppler-24.08.0\Library\bin"
        images = convert_from_path(check_path, poppler_path=poppler_path)
        if not images:
            logger.error("No images extracted from PDF")
            return
            
        # Convert first page to bytes
        img_byte_arr = io.BytesIO()
        images[0].save(img_byte_arr, format='PNG')
        img_bytes = base64.b64encode(img_byte_arr.getvalue()).decode('utf-8')
        
        # Create request for Nova Lite
        system_list = [{
            "text": "You are an expert at analyzing check images. Extract key information accurately and format it clearly."
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
                    "text": "Please analyze this check image and extract:\n1. Payee Name\n2. Amount (both numerical and written)\n3. Date\n4. Check Number\n5. Account Holder Name\n\nReturn the information in a structured format."
                }
            ]
        }]
        
        request = {
            "schemaVersion": "messages-v1",
            "messages": message_list,
            "system": system_list,
            "inferenceConfig": {
                "max_new_tokens": 1000,
                "top_p": 0.9,
                "top_k": 250,
                "temperature": 0.1
            }
        }
        
        # Test Nova Lite
        logger.debug("Testing Nova Lite...")
        try:
            lite_response = await nova_lite.analyze_check_image(request)
            logger.info("Nova Lite Response:")
            logger.info(lite_response)
        except Exception as e:
            logger.error(f"Nova Lite Error: {str(e)}")
            logger.error(traceback.format_exc())
        
        # Test Nova Pro with same request
        logger.debug("Testing Nova Pro...")
        try:
            pro_response = await nova_pro.match_data(request)
            logger.info("Nova Pro Response:")
            logger.info(pro_response)
        except Exception as e:
            logger.error(f"Nova Pro Error: {str(e)}")
            logger.error(traceback.format_exc())
        
    except Exception as e:
        logger.error(f"Error in main: {str(e)}")
        logger.error(traceback.format_exc())

if __name__ == "__main__":
    asyncio.run(main())
