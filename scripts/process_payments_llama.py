import os
import sys
import json
import logging
import datetime
import asyncio
from pathlib import Path
import glob
import re
import fitz
import random
from Levenshtein import distance as Levenshtein_distance

# Add project root to path
project_root = str(Path(__file__).parent.parent)
sys.path.append(project_root)

from src.llama_client import LlamaClient
import tkinter as tk
from tkinter import filedialog

# Initialize Llama client
try:
    llama_client = LlamaClient()
except Exception as e:
    logger = logging.getLogger(__name__)
    logger.error(f"Failed to initialize LlamaClient: {str(e)}")
    sys.exit(1)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Add file handler
log_dir = os.path.join(project_root, 'logs')
os.makedirs(log_dir, exist_ok=True)
timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
log_file = os.path.join(log_dir, f'process_payments_{timestamp}.log')
file_handler = logging.FileHandler(log_file)
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logger.addHandler(file_handler)

logger.info(f"Detailed logs will be written to: {log_file}")

async def analyze_check_image(pdf_path: str) -> dict:
    """
    Analyze a check image and extract relevant information using the LlamaClient API.
    """
    try:
        # Convert first page of PDF to PNG
        doc = fitz.open(pdf_path)
        page = doc[0]
        
        # Convert to PNG
        pix = page.get_pixmap()
        png_path = pdf_path.replace('.pdf', '.png')
        pix.save(png_path)
        logger.info(f"Saved check image as PNG: {png_path}")
        
        doc.close()
        
        # Call LlamaClient API
        check_data = await llama_client.extract_check_info(Path(png_path))
        
        # Add file paths to result
        check_data['pdf_path'] = pdf_path
        check_data['image_path'] = png_path
        return check_data
            
    except Exception as e:
        logger.error(f"Error analyzing check image {pdf_path}: {str(e)}")
        return None

def normalize_name(name: str) -> str:
    """Normalize a name for comparison"""
    # Remove room numbers and common titles
    name = re.sub(r'\s+\d+\s*$', '', name)
    name = re.sub(r'^(Mr\.|Mrs\.|Ms\.|Dr\.)\s+', '', name, flags=re.IGNORECASE)
    
    # Convert to lowercase and remove punctuation
    name = name.lower()
    name = re.sub(r'[^\w\s]', '', name)
    
    # Remove extra whitespace
    name = ' '.join(name.split())
    
    return name

def name_similarity(name1: str, name2: str) -> float:
    """Calculate similarity between two names"""
    try:
        name1 = normalize_name(name1)
        name2 = normalize_name(name2)
        
        # Use Levenshtein distance for fuzzy matching
        max_len = max(len(name1), len(name2))
        if max_len == 0:
            return 0.0
            
        distance = Levenshtein_distance(name1, name2)
        similarity = 1 - (distance / max_len)
        
        return similarity
        
    except Exception as e:
        logger.error(f"Error calculating name similarity: {str(e)}")
        return 0.0

def normalize_amount(amount_str: str) -> float:
    """Convert amount string to float"""
    try:
        # Remove $ and , from amount
        amount = amount_str.replace('$', '').replace(',', '')
        return float(amount)
    except (ValueError, AttributeError) as e:
        logger.error(f"Error normalizing amount {amount_str}: {str(e)}")
        return 0.0

def get_date_score(date1_str: str, date2_str: str) -> float:
    """Calculate similarity score between two dates"""
    try:
        if not date1_str or not date2_str:
            return 0.0
            
        date1 = datetime.datetime.strptime(date1_str, '%m/%d/%Y')
        date2 = datetime.datetime.strptime(date2_str, '%m/%d/%Y')
        
        # Calculate days difference
        days_diff = abs((date2 - date1).days)
        
        # Score decreases as days difference increases
        # Perfect score (1.0) if same day
        # 0.9 if within a week
        # 0.8 if within a month
        # 0.0 if more than 3 months
        if days_diff == 0:
            return 1.0
        elif days_diff <= 7:
            return 0.9
        elif days_diff <= 30:
            return 0.8
        elif days_diff <= 90:
            return 0.5
        else:
            return 0.0
            
    except (ValueError, TypeError) as e:
        logger.error(f"Error calculating date score: {str(e)}")
        return 0.0

def is_match(check: dict, invoice: dict) -> bool:
    """Determine if a check matches an invoice"""
    try:
        # Get normalized amounts
        check_amount = normalize_amount(check['amount'])
        invoice_amount = normalize_amount(invoice['amount'])
        
        # Check if amounts are within 5% of each other
        amount_diff = abs(check_amount - invoice_amount)
        amount_threshold = invoice_amount * 0.05
        amount_matches = amount_diff <= amount_threshold
        
        # Compare names with fuzzy matching
        name_score = name_similarity(check['payee'], invoice['payee'])
        name_matches = name_score >= 0.6
        
        # Compare dates
        date_score = get_date_score(check['date'], invoice['date'])
        date_matches = date_score >= 0.3
        
        logger.debug(f"Match scores for check {check['check_number']} and invoice {invoice['invoice_number']}:")
        logger.debug(f"Amount match: {amount_matches} (diff: {amount_diff}, threshold: {amount_threshold})")
        logger.debug(f"Name match: {name_matches} (score: {name_score})")
        logger.debug(f"Date match: {date_matches} (score: {date_score})")
        
        # Return True if all criteria match
        return amount_matches and name_matches and date_matches
        
    except Exception as e:
        logger.error(f"Error checking match: {str(e)}")
        return False

def match_checks_with_invoices(checks: list, invoices: list) -> tuple:
    """
    Match checks with invoices using fuzzy matching
    Returns (matches, unmatched_checks, unmatched_invoices)
    """
    matches = []
    unmatched_checks = []
    matched_invoice_ids = set()
    
    # Try to match each check
    for check in checks:
        found_match = False
        best_match = None
        best_score = 0
        
        for invoice in invoices:
            if invoice['invoice_number'] in matched_invoice_ids:
                continue
                
            # Calculate match scores
            amount_score = 0
            check_amount = normalize_amount(check['amount'])
            invoice_amount = normalize_amount(invoice['amount'])
            amount_diff = abs(check_amount - invoice_amount)
            amount_threshold = invoice_amount * 0.05
            if amount_diff <= amount_threshold:
                amount_score = 1 - (amount_diff / amount_threshold)
            
            name_score = name_similarity(check['payee'], invoice['payee'])
            date_score = get_date_score(check['date'], invoice['date'])
            
            # Calculate weighted score
            overall_score = (amount_score * 0.5) + (name_score * 0.3) + (date_score * 0.2)
            
            # Log scores for debugging
            logger.debug(f"Check {check['check_number']} vs Invoice {invoice['invoice_number']}:")
            logger.debug(f"Amount score: {amount_score:.2f} (check: ${check_amount:.2f}, invoice: ${invoice_amount:.2f})")
            logger.debug(f"Name score: {name_score:.2f} (check: {check['payee']}, invoice: {invoice['payee']})")
            logger.debug(f"Date score: {date_score:.2f} (check: {check['date']}, invoice: {invoice['date']})")
            logger.debug(f"Overall score: {overall_score:.2f}")
            
            if overall_score > best_score:
                best_score = overall_score
                best_match = invoice
                found_match = True
        
        if found_match and best_match and best_score >= 0.6:
            matches.append({
                'check': check,
                'invoice': best_match,
                'match_score': best_score
            })
            matched_invoice_ids.add(best_match['invoice_number'])
            logger.info(f"Matched check #{check['check_number']} with invoice {best_match['invoice_number']} (score: {best_score:.2f})")
        else:
            unmatched_checks.append(check)
            logger.warning(f"No match found for check #{check['check_number']} (best score: {best_score:.2f})")
    
    # Get unmatched invoices
    unmatched_invoices = [inv for inv in invoices if inv['invoice_number'] not in matched_invoice_ids]
    
    logger.info(f"Matching complete: {len(matches)} matches, {len(unmatched_checks)} unmatched checks, {len(unmatched_invoices)} unmatched invoices")
    
    return matches, unmatched_checks, unmatched_invoices

async def process_input_folder(folder_path: str):
    """Process all files in the input folder"""
    try:
        # Process check images
        check_data = []
        check_files = glob.glob(os.path.join(folder_path, '*.pdf'))
        
        for check_file in check_files:
            logger.info(f"Processing check: {os.path.basename(check_file)}")
            check_result = await analyze_check_image(check_file)
            if check_result:
                check_data.append(check_result)
        
        # Load billing data
        billing_file = os.path.join(folder_path, 'billing_download_20241228.json')
        logger.info(f"Using Knack billing data from: billing_download_20241228.json")
        with open(billing_file, 'r') as f:
            raw_billing_data = json.load(f)
            
        # Convert billing data to our format
        billing_data = []
        for invoice in raw_billing_data:
            try:
                # Extract amount from field_1411 (total amount)
                amount = float(invoice.get('field_1411_raw', 0))
                
                # Extract payee from field_1350 (removing HTML tags)
                raw_payee = invoice.get('field_1350', '')
                payee = re.sub(r'<[^>]+>', '', raw_payee)
                
                # Extract resident name from field_1350_raw
                resident_name = ''
                if invoice.get('field_1350_raw'):
                    raw_data = invoice['field_1350_raw']
                    if isinstance(raw_data, list) and len(raw_data) > 0:
                        resident_name = raw_data[0].get('identifier', '')
                
                # Get invoice date from field_1351
                invoice_date = invoice.get('field_1351', '')
                if not invoice_date and invoice.get('field_1351_raw'):
                    invoice_date = invoice['field_1351_raw'].get('date', '')
                
                # Get invoice number from field_1418
                invoice_number = invoice.get('field_1418', '')
                
                billing_data.append({
                    'invoice_number': invoice_number,
                    'amount': f"${amount:,.2f}",
                    'date': invoice_date,
                    'payee': payee,
                    'resident_name': resident_name,
                    'raw_payee': raw_payee
                })
            except (ValueError, KeyError) as e:
                logger.warning(f"Error processing invoice {invoice.get('field_1418', 'N/A')}: {str(e)}")
                continue
        
        # Save parsed data for debugging
        debug_file = os.path.join(folder_path, 'parsed_data_debug.json')
        with open(debug_file, 'w') as f:
            json.dump({
                'check_data': check_data,
                'invoice_data': billing_data
            }, f, indent=2)
        logger.info(f"Saved parsed data for debugging to: {debug_file}")
        
        # Load bank statement data
        bank_file = os.path.join(folder_path, 'stmt.csv')
        logger.info(f"Using bank data from: stmt.csv")
        
        # Match checks with invoices
        logger.info("Starting match with Python logic...")
        try:
            matches, unmatched_checks, unmatched_invoices = match_checks_with_invoices(check_data, billing_data)
            
            # Save matches for review
            matches_file = os.path.join(folder_path, 'matches.json')
            with open(matches_file, 'w') as f:
                json.dump({
                    'matched_payments': matches,
                    'unmatched_checks': unmatched_checks,
                    'unmatched_invoices': unmatched_invoices
                }, f, indent=2)
            logger.info(f"Saved matches to: {matches_file}")
            
            return matches
            
        except Exception as e:
            logger.error(f"Error matching checks with invoices: {str(e)}")
            raise
        
    except Exception as e:
        logger.error(f"Error processing input folder: {str(e)}")
        raise

def get_input_folder():
    """Get input folder from user."""
    try:
        root = tk.Tk()
        root.withdraw()
        folder_path = filedialog.askdirectory(
            title="Select folder containing PDFs and data files"
        )
        
        if not folder_path:
            logger.error("No folder selected")
            return None
            
        # Normalize path
        folder_path = os.path.normpath(folder_path)
        
        # Check that required files exist
        pdf_files = glob.glob(os.path.join(folder_path, '*.pdf'))
        if not pdf_files:
            logger.error("No PDF files found in selected folder")
            return None
            
        billing_files = glob.glob(os.path.join(folder_path, 'billing_download*.json'))
        if not billing_files:
            logger.error("No billing_download*.json file found in selected folder")
            return None
            
        bank_files = glob.glob(os.path.join(folder_path, 'stmt*.csv'))
        if not bank_files:
            logger.error("No stmt*.csv file found in selected folder")
            return None
            
        return folder_path
        
    except Exception as e:
        logger.error(f"Error getting input folder: {str(e)}")
        return None
    finally:
        if 'root' in locals():
            root.destroy()

async def show_matching_gui(check, potential_matches):
    """Show GUI for manual matching."""
    try:
        # Create root window
        root = tk.Tk()
        root.title("Check Matching")
        root.geometry("800x600")
        
        # Create frame for check info
        check_frame = tk.LabelFrame(root, text="Check Information", padx=10, pady=10)
        check_frame.pack(fill="x", padx=10, pady=5)
        
        # Show check info
        tk.Label(check_frame, text=f"Check #: {check.get('check_number', 'N/A')}").pack()
        tk.Label(check_frame, text=f"Amount: {check.get('amount', 'N/A')}").pack()
        tk.Label(check_frame, text=f"Date: {check.get('date', 'N/A')}").pack()
        tk.Label(check_frame, text=f"From: {check.get('from', 'N/A')}").pack()
        
        # Create frame for matches
        matches_frame = tk.LabelFrame(root, text="Potential Matches", padx=10, pady=10)
        matches_frame.pack(fill="both", expand=True, padx=10, pady=5)
        
        # Create scrollable frame for matches
        canvas = tk.Canvas(matches_frame)
        scrollbar = tk.Scrollbar(matches_frame, orient="vertical", command=canvas.yview)
        scrollable_frame = tk.Frame(canvas)
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # Pack scrollbar and canvas
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        
        # Variable to store selected match
        selected_match = [None]  # Use list to allow modification in inner function
        
        def select_match(match):
            selected_match[0] = match
            root.quit()
        
        def skip_match():
            selected_match[0] = None
            root.quit()
        
        # Add matches
        for match in potential_matches:
            match_frame = tk.Frame(scrollable_frame, relief="raised", borderwidth=1)
            match_frame.pack(fill="x", padx=5, pady=5)
            
            tk.Label(match_frame, text=f"Invoice #: {match.get('invoice_number', 'N/A')}").pack()
            tk.Label(match_frame, text=f"Amount: ${match.get('amount', 0):,.2f}").pack()
            tk.Label(match_frame, text=f"Date: {match.get('date', 'N/A')}").pack()
            tk.Label(match_frame, text=f"Payee: {match.get('payee', 'N/A')}").pack()
            tk.Label(match_frame, text=f"Confidence: {match.get('confidence', 0):.2%}").pack()
            tk.Label(match_frame, text=f"Reasoning: {match.get('reasoning', 'N/A')}").pack()
            
            tk.Button(
                match_frame,
                text="Select",
                command=lambda m=match: select_match(m)
            ).pack(pady=5)
        
        # Add skip button at bottom
        tk.Button(
            root,
            text="Skip (No Match)",
            command=skip_match
        ).pack(pady=10)
        
        # Run GUI
        root.mainloop()
        
        # Clean up
        root.destroy()
        
        return selected_match[0]
        
    except Exception as e:
        logger.error(f"Error showing matching GUI: {str(e)}")
        return None

async def main():
    """Main function to process payments"""
    try:
        # Get input folder
        folder_path = get_input_folder()
        if not folder_path:
            logger.error("No input folder selected")
            return
            
        # Process all files in the folder
        matches = await process_input_folder(folder_path)
        if not matches:
            logger.error("Failed to get matches")
            return
            
        logger.info("Processing complete!")
        
    except Exception as e:
        logger.error(f"Error in main: {str(e)}")
        
if __name__ == '__main__':
    asyncio.run(main())
