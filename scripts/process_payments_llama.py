import os
import sys
import json
import logging
import asyncio
from pathlib import Path
import glob
import re
import fitz  # PyMuPDF
import random
from Levenshtein import distance as Levenshtein_distance
from typing import Optional, Dict
import tkinter as tk
from tkinter import filedialog
from datetime import datetime
from difflib import SequenceMatcher

# Add project root to path
project_root = str(Path(__file__).parent.parent)
sys.path.append(project_root)

from src.llama_client import LlamaClient

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
timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
log_file = os.path.join(log_dir, f'process_payments_{timestamp}.log')
file_handler = logging.FileHandler(log_file)
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logger.addHandler(file_handler)

logger.info(f"Detailed logs will be written to: {log_file}")

async def convert_pdf_to_png(pdf_path: str, dpi: int = 300) -> str:
    """Convert first page of PDF to PNG with specified DPI."""
    try:
        # Get directory and filename from pdf_path
        dir_path = os.path.dirname(pdf_path)
        base_name = os.path.splitext(os.path.basename(pdf_path))[0]
        png_path = os.path.join(dir_path, f"{base_name}.png")
        
        print(f"Converting PDF to PNG:")
        print(f"  PDF path: {pdf_path}")
        print(f"  PNG path: {png_path}")
        
        # Convert first page of PDF to PNG
        doc = fitz.open(pdf_path)
        page = doc[0]
        
        # Set matrix for higher resolution
        zoom = dpi / 72  # Default DPI is 72
        matrix = fitz.Matrix(zoom, zoom)
        
        # Convert to PNG with higher resolution
        pix = page.get_pixmap(matrix=matrix)
        pix.save(png_path)
        print(f"  Saved PNG file: {os.path.getsize(png_path)} bytes")
        logger.info(f"Saved check image as PNG: {png_path}")
        
        doc.close()
        return png_path
        
    except Exception as e:
        error_msg = f"Error converting PDF to PNG {pdf_path}: {str(e)}"
        print(f"  ERROR: {error_msg}")
        logger.error(error_msg)
        return None

async def analyze_check_image(pdf_path: str, png_path: str) -> dict:
    """
    Analyze a check image and extract relevant information using the LlamaClient API.
    """
    try:
        # Call LlamaClient API
        check_data = await llama_client.extract_check_info(Path(png_path))
        if not check_data:
            return None
        
        # Add file paths to result
        check_data['pdf_path'] = pdf_path
        check_data['image_path'] = png_path
        return check_data
            
    except Exception as e:
        logger.error(f"Error analyzing check image {pdf_path}: {str(e)}")
        return None

async def analyze_check_with_consensus(check_file: str, num_attempts: int = 2) -> Optional[Dict]:
    """Analyze a check multiple times and use consensus."""
    # First convert PDF to PNG once
    png_path = await convert_pdf_to_png(check_file)
    if not png_path:
        return None
    
    results = []
    for i in range(num_attempts):
        logger.info(f"Attempt {i+1} analyzing check: {os.path.basename(check_file)}")
        result = await analyze_check_image(check_file, png_path)
        if result:
            results.append(result)
    
    if not results:
        logger.warning(f"No valid results from {num_attempts} attempts")
        return None
        
    # If all results are identical, use that
    if all(result == results[0] for result in results):
        logger.info("All attempts returned identical results")
        return results[0]
        
    # If we have different results, try two more times
    if num_attempts == 2:
        logger.info("Results differ, trying two more times")
        for i in range(2):
            logger.info(f"Additional attempt {i+1} analyzing check: {os.path.basename(check_file)}")
            result = await analyze_check_image(check_file, png_path)
            if result:
                results.append(result)
    
    # Take the most common result for each field
    consensus = {}
    required_fields = ['check_number', 'amount', 'date', 'payee', 'from', 'from_address', 'memo', 'bank_name']
    
    for field in required_fields:
        values = [result.get(field) for result in results if result.get(field)]
        if values:
            # Get most common value
            from collections import Counter
            value_counts = Counter(values)
            consensus[field] = value_counts.most_common(1)[0][0]
    
    # Ensure we have all required fields
    if all(field in consensus for field in ['check_number', 'amount', 'date', 'payee', 'from']):
        logger.info("Generated consensus from multiple attempts")
        return consensus
    
    logger.warning("Could not reach consensus on all required fields")
    return None

def normalize_name(name: str) -> str:
    """Normalize a name for comparison"""
    if not name:
        return ''
        
    # Remove unit numbers (e.g. "Kurt Elliott 413" -> "Kurt Elliott")
    name = re.sub(r'\s+\d+$', '', name)
    
    # Convert to lowercase and remove punctuation
    name = name.lower()
    name = re.sub(r'[^\w\s]', '', name)
    
    # Sort words to handle different name orders
    words = name.split()
    words.sort()
    
    return ' '.join(words)

def name_similarity(name1: str, name2: str) -> float:
    """Calculate similarity between two names"""
    try:
        if not name1 or not name2:
            return 0.0
            
        # Normalize both names
        name1 = normalize_name(name1)
        name2 = normalize_name(name2)
        
        # Split into words
        words1 = set(name1.split())
        words2 = set(name2.split())
        
        # Calculate word overlap
        common_words = words1.intersection(words2)
        total_words = words1.union(words2)
        
        if not total_words:
            return 0.0
            
        # Score based on word overlap
        return len(common_words) / len(total_words)
        
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
            
        date1 = datetime.strptime(date1_str, '%m/%d/%Y')
        date2 = datetime.strptime(date2_str, '%m/%d/%Y')
        
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

def is_match(check: dict, invoice: dict) -> float:
    """Determine if a check matches an invoice"""
    try:
        # Convert amounts to float for comparison
        check_amount = normalize_amount(check['amount'])
        invoice_amount = normalize_amount(invoice['amount'])
        
        # Calculate amount similarity (0-1)
        amount_diff = abs(check_amount - invoice_amount)
        amount_score = 1.0 if amount_diff == 0 else max(0, 1.0 - (amount_diff / max(check_amount, invoice_amount)))
        
        # Calculate date similarity (0-1)
        date_score = get_date_score(check['date'], invoice['date'])
        
        # Calculate name similarity (0-1)
        from_name = normalize_name(check['from'])
        resident_name = normalize_name(invoice['resident_name'])
        name_score = name_similarity(from_name, resident_name)
        
        # Calculate payee similarity (0-1)
        check_payee = normalize_name(check['payee'])
        invoice_payee = normalize_name(invoice['payee'])
        payee_score = name_similarity(check_payee, invoice_payee)
        
        # Weight the scores (adjust weights as needed)
        amount_weight = 0.4  # Amount is very important
        date_weight = 0.2   # Date is somewhat important
        name_weight = 0.3   # From name is important
        payee_weight = 0.1  # Payee is less important since it's often just "The Mapleton"
        
        total_score = (
            amount_score * amount_weight +
            date_score * date_weight +
            name_score * name_weight +
            payee_score * payee_weight
        )
        
        return total_score
        
    except Exception as e:
        logger.error(f"Error comparing check and invoice: {str(e)}")
        return 0.0

def match_checks_with_invoices(checks: list, invoices: list) -> tuple:
    """
    Match checks with invoices using fuzzy matching
    Returns (matches, unmatched_checks, unmatched_invoices)
    """
    # Convert Knack billing data to our format
    formatted_invoices = []
    for invoice in invoices:
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
            
            formatted_invoices.append({
                'invoice_number': invoice_number,
                'amount': f"${amount:,.2f}",
                'date': invoice_date,
                'payee': payee,
                'resident_name': resident_name,
                'raw_payee': raw_payee,
                'original_data': invoice  # Keep original data for reference
            })
        except (ValueError, KeyError) as e:
            logger.warning(f"Error processing invoice {invoice.get('field_1418', 'N/A')}: {str(e)}")
            continue

    # For each check, find all potential matches sorted by score
    matches = []
    unmatched_checks = []
    matched_invoices = set()
    
    for check in checks:
        # Get match scores for all invoices
        scored_matches = []
        for invoice in formatted_invoices:
            score = is_match(check, invoice)
            if score > 0.3:  # Only consider matches with at least 30% confidence
                scored_matches.append({
                    'check': check,
                    'invoice': invoice,
                    'confidence': score
                })
        
        if scored_matches:
            # Sort by confidence score
            scored_matches.sort(key=lambda x: x['confidence'], reverse=True)
            matches.append(scored_matches)
        else:
            unmatched_checks.append(check)
            
        # Track which invoices were matched
        for match in scored_matches:
            matched_invoices.add(match['invoice']['invoice_number'])
    
    # Find unmatched invoices
    unmatched_invoices = [inv for inv in formatted_invoices 
                         if inv['invoice_number'] not in matched_invoices]
    
    return matches, unmatched_checks, unmatched_invoices

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

async def process_input_folder(folder_path: str) -> tuple:
    """Process all files in the input folder"""
    print(f"\nProcessing files in folder: {folder_path}")
    pdf_files = [f for f in os.listdir(folder_path) if f.endswith('.pdf')]
    print(f"Found PDF files: {pdf_files}")
    check_data = []
    
    for pdf_file in pdf_files:
        pdf_path = os.path.join(folder_path, pdf_file)
        print(f"\nProcessing PDF: {pdf_path}")
        
        # Extract check number from filename
        check_number = os.path.splitext(pdf_file)[0]
        
        # Convert to PNG and analyze
        png_path = os.path.join(folder_path, f"{check_number}.png")
        print(f"Will save PNG to: {png_path}")
        await convert_pdf_to_png(pdf_path)
        
        # Verify PNG was created
        if os.path.exists(png_path):
            print(f"PNG file created successfully: {png_path}")
            print(f"PNG file size: {os.path.getsize(png_path)} bytes")
        else:
            print(f"WARNING: PNG file was not created at {png_path}")
        
        # Analyze check with consensus
        check_info = await analyze_check_with_consensus(pdf_path)
        if check_info:
            # Add file paths to check info
            check_info['pdf_path'] = pdf_path
            check_info['png_path'] = png_path
            print(f"Added to check data with paths:")
            print(f"  PDF: {check_info['pdf_path']}")
            print(f"  PNG: {check_info['png_path']}")
            check_data.append(check_info)
    
    return check_data

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
