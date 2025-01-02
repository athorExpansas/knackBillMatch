import asyncio
import os
import glob
import tkinter as tk
from tkinter import filedialog, messagebox
from datetime import datetime
import json

# Add project root to path
import sys
from pathlib import Path
project_root = str(Path(__file__).parent)
sys.path.append(project_root)

from scripts.download_billings import main as download_billings
from scripts.process_payments_llama import process_input_folder as process_checks
from scripts.matching_gui import show_matching_gui
from scripts.matcher import match_payments

def check_required_files(folder_path):
    """Check if all required files are present in the folder."""
    pdfs = glob.glob(os.path.join(folder_path, "*.pdf"))
    epayment_reports = glob.glob(os.path.join(folder_path, "rpt*.csv"))
    bank_transactions = glob.glob(os.path.join(folder_path, "stmt*.csv"))
    
    missing_files = []
    if not pdfs:
        missing_files.append("PDF check files")
    if not epayment_reports:
        missing_files.append("Bill.com ePayment details report (rpt*.csv)")
    if not bank_transactions:
        missing_files.append("Bank of America transactions (stmt*.csv)")
    
    return missing_files

async def main():
    # Create root window but hide it
    root = tk.Tk()
    root.withdraw()
    
    # Step 1: Ask for folder and check required files
    folder_path = filedialog.askdirectory(title="Select folder containing payment files")
    if not folder_path:
        print("No folder selected. Exiting...")
        return
    
    missing_files = check_required_files(folder_path)
    if missing_files:
        print("\nMissing required files in the selected folder:")
        for file in missing_files:
            print(f"- {file}")
        print("\nPlease ensure all required files are present in the folder:")
        print("1. PDF files containing check images")
        print("2. Bill.com ePayment details report (filename starting with 'rpt')")
        print("3. Bank of America transactions (filename starting with 'stmt')")
        return
    
    # Step 2: Download latest billings
    print("\nDownloading latest billings...")
    billings = await download_billings(folder_path)
    
    # Step 3: Process checks with OCR
    print("\nProcessing checks with OCR...")
    check_data = await process_checks(folder_path)
    if not check_data:
        print("No check data was processed. Exiting...")
        return
    
    # Step 4: Match payments
    print("\nMatching payments with billings...")
    matches = match_payments(check_data, billings)
    
    # Step 5: Show GUI for reviewing matches
    print("\nLaunching GUI for match review...")
    final_matches = show_matching_gui(check_data, matches)
    
    if final_matches:
        # Save final matches
        output_file = os.path.join(folder_path, f"final_matches_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
        with open(output_file, 'w') as f:
            json.dump(final_matches, f, indent=2)
        print(f"\nFinal matches saved to: {output_file}")
        
        # Step 6: Update Knack DB (placeholder for now)
        print("\nUpdating Knack database...")
        # TODO: Implement update_knack_billings.py and call it here
        print("Note: Knack database update functionality is pending implementation")
    else:
        print("\nNo matches were finalized. Exiting without saving...")

if __name__ == "__main__":
    asyncio.run(main())
