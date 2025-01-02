import asyncio
import logging
from pathlib import Path
import sys
import tkinter as tk
from tkinter import filedialog

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

async def get_file_paths():
    """Test file selection dialog"""
    logger.debug("Creating root window...")
    root = tk.Tk()
    root.withdraw()  # Hide the main window
    
    logger.debug("Opening file dialog...")
    statement_path = filedialog.askopenfilename(
        title="Select Bank Statement CSV",
        filetypes=[("CSV files", "*.csv")]
    )
    logger.debug(f"Selected statement: {statement_path}")
    
    logger.debug("Opening folder dialog...")
    checks_folder = filedialog.askdirectory(
        title="Select Check Images Folder"
    )
    logger.debug(f"Selected folder: {checks_folder}")
    
    logger.debug("Opening file dialog...")
    billing_json = filedialog.askopenfilename(
        title="Select Billing Data JSON",
        filetypes=[("JSON files", "*.json")]
    )
    logger.debug(f"Selected billing: {billing_json}")
    
    root.destroy()
    return statement_path, checks_folder, billing_json

async def main():
    try:
        logger.debug("Creating NovaClient...")
        nova = NovaClient()
        
        logger.debug("Initializing NovaClient...")
        await nova.initialize()
        logger.debug("NovaClient initialized successfully!")
        
        logger.debug("Testing file dialogs...")
        statement, checks, billing = await get_file_paths()
        logger.debug("File paths obtained successfully!")
        
    except Exception as e:
        logger.error(f"Error: {e}")
        raise

if __name__ == "__main__":
    asyncio.run(main())
