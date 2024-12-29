import asyncio
import json
import logging
from pathlib import Path
import sys
import base64
from pdf2image import convert_from_path
import io
from typing import List, Dict
import os
import tkinter as tk
from tkinter import filedialog
import datetime
import glob

# Add project root to path
project_root = str(Path(__file__).parent.parent)
sys.path.append(project_root)

# Configure logging
log_dir = Path(project_root) / "logs"
log_dir.mkdir(exist_ok=True)

timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
log_file = log_dir / f"process_payments_{timestamp}.log"

# Set up file handler
file_handler = logging.FileHandler(log_file)
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))

# Set up console handler with less verbose output
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))

# Configure root logger
logging.basicConfig(level=logging.DEBUG, handlers=[file_handler, console_handler])

# Get logger for this module
logger = logging.getLogger(__name__)

# Configure boto logging
boto_logger = logging.getLogger('botocore')
boto_logger.setLevel(logging.DEBUG)
# Remove any existing handlers to avoid duplicate logs
for handler in boto_logger.handlers[:]:
    boto_logger.removeHandler(handler)
boto_logger.addHandler(file_handler)

# Configure urllib3 logging
urllib3_logger = logging.getLogger('urllib3')
urllib3_logger.setLevel(logging.DEBUG)
for handler in urllib3_logger.handlers[:]:
    urllib3_logger.removeHandler(handler)
urllib3_logger.addHandler(file_handler)

logger.info(f"Detailed logs will be written to: {log_file}")

from src.nova_client import NovaLiteClient, NovaProClient

async def analyze_check_image(nova_lite: NovaLiteClient, pdf_path: str) -> Dict:
    """Analyze a single check image using Nova"""
    logger.info(f"Converting PDF to image: {Path(pdf_path).name}")
    
    # Convert PDF to image
    poppler_path = r"C:\poppler\poppler-24.08.0\Library\bin"
    images = convert_from_path(pdf_path, poppler_path=poppler_path)
    if not images:
        logger.error(f"No images extracted from PDF: {Path(pdf_path).name}")
        return None
        
    # Take first page and convert to bytes
    img_byte_arr = io.BytesIO()
    images[0].save(img_byte_arr, format='PNG')
    img_bytes = base64.b64encode(img_byte_arr.getvalue()).decode('utf-8')
    
    # Create request
    system_list = [{
        "text": "You are an expert at analyzing check images. Extract key information accurately and format it clearly. Focus ONLY on the check image itself - completely ignore any bank statements, transaction details, or other information that might appear above or around the check."
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
                "text": "Please analyze ONLY the check image itself. Completely ignore any bank statements or transaction details that might appear above or around the check.\n\nFrom the check image ONLY, extract:\n1. Payee Name (Pay to the Order of)\n2. Amount (both numerical and written)\n3. Date on the check\n4. Check Number\n5. Drawer/Account Holder Name\n\nAfter listing the extracted information, please add:\n6. Additional Review Required (Yes/No): Indicate if any fields ON THE CHECK ITSELF were unclear, hard to read, or if there are discrepancies between numerical and written amounts ON THE CHECK. If yes, explain why. Do not compare with any transaction details outside the check.\n\nReturn the information in a structured format that can be easily parsed."
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
    
    try:
        response = await nova_lite.analyze_check_image(request)
        if response:
            # Parse the response into a structured format
            raw_response = response.strip('`json\n{}').strip()
            parsed_response = json.loads('{' + raw_response + '}')
            result = {
                'pdf_path': pdf_path,
                'raw_response': response,  # Keep the raw response for Nova Pro
                'check_number': parsed_response.get('Check Number', ''),
                'amount': float(parsed_response.get('Amount', {}).get('Numerical', '0')),
                'written_amount': parsed_response.get('Amount', {}).get('Written', ''),
                'date': parsed_response.get('Date on the check', ''),
                'payee': parsed_response.get('Payee Name', ''),
                'drawer': parsed_response.get('Drawer/Account Holder Name', ''),
                'needs_review': 'yes' in response.lower() and 'review required' in response.lower()
            }
            
            # Log only essential information
            logger.info(f"Successfully processed {Path(pdf_path).name}")
            if result['needs_review']:
                logger.warning(f"Check {Path(pdf_path).name} needs review")
                
            return result
            
    except Exception as e:
        logger.error(f"Error analyzing check {Path(pdf_path).name}: {str(e)}")
        return None

async def reanalyze_check(nova_lite: NovaLiteClient, check_result: Dict) -> Dict:
    """Re-analyze a check when the amount is questionable"""
    try:
        logger.info(f"Re-analyzing check {Path(check_result['pdf_path']).name} due to amount discrepancy")
        
        # Convert PDF to base64
        with open(check_result['pdf_path'], 'rb') as f:
            pdf_bytes = f.read()
        pdf_base64 = base64.b64encode(pdf_bytes).decode('utf-8')
        
        # Create request with focus on amount verification
        request = {
            "image": pdf_base64,
            "focus": "amount_verification",
            "previous_analysis": check_result
        }
        
        # Get new analysis
        new_response = await nova_lite.analyze_check_image(request)
        if new_response:
            new_result = json.loads(new_response)
            
            # Compare results
            if new_result.get('Amount Confidence') == 'HIGH':
                logger.info(f"Re-analysis successful - new amount: ${new_result['Amount']['Numerical']}")
                return new_result
            else:
                logger.warning(f"Re-analysis still uncertain about amount")
                return check_result
                
    except Exception as e:
        logger.error(f"Error in reanalyze_check: {str(e)}")
        return check_result

async def match_checks_with_invoices(nova_pro: NovaProClient, nova_lite: NovaLiteClient, check_data: List[Dict], invoice_data: List[Dict], bank_data_str: str) -> Dict:
    """Match analyzed checks with invoice data using Nova Pro"""
    
    # Filter check data to essential fields and parse amounts
    filtered_checks = []
    checks_needing_reanalysis = []
    
    for check in check_data:
        try:
            filtered_check = {
                'check_id': Path(check['pdf_path']).stem,
                'amount': check['amount'],
                'date': check['date'],
                'payee': check['payee'],
                'check_number': check['check_number'],
                'amount_confidence': check.get('Amount Confidence', 'UNKNOWN')
            }
            filtered_checks.append(filtered_check)
            
            # Flag checks that might need reanalysis
            if check.get('Amount Confidence') == 'LOW':
                checks_needing_reanalysis.append(check)
                
        except Exception as e:
            logger.error(f"Error parsing check data: {str(e)}")
            continue
    
    # Get initial matches
    logger.info("Getting initial matches from Nova Pro...")
    request = {
        'checks': filtered_checks,
        'invoices': invoice_data,
        'bank_data': bank_data_str
    }
    
    matches = await nova_pro.match_data(request)
    logger.debug(f"Nova Pro response: {matches}")
    
    try:
        # Extract JSON from markdown response
        json_blocks = matches.split("```json")
        if len(json_blocks) > 1:
            # Take the last JSON block
            json_text = json_blocks[-1].split("```")[0].strip()
            logger.debug(f"Extracted JSON: {json_text}")
            matches_data = json.loads(json_text)
        else:
            # Try parsing the whole response as JSON
            matches_data = json.loads(matches)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse Nova Pro response: {str(e)}")
        logger.error(f"Response content: {matches}")
        raise
    
    # Check for close amount matches that might benefit from check reanalysis
    for match in matches_data:
        for invoice in match.get('matching_invoices', []):
            amount_diff = abs(match['amount'] - invoice['amount'])
            if amount_diff <= 50 and match['check_id'] in [c['check_id'] for c in filtered_checks]:
                # Find original check data
                original_check = next(c for c in check_data if Path(c['pdf_path']).stem == match['check_id'])
                
                # Re-analyze check if we haven't already
                if original_check not in checks_needing_reanalysis:
                    logger.info(f"Small amount difference (${amount_diff:.2f}) detected, re-analyzing check {match['check_id']}")
                    new_analysis = await reanalyze_check(nova_lite, original_check)
                    
                    # If re-analysis gives different amount, update and re-match
                    if new_analysis and abs(new_analysis['Amount']['Numerical'] - original_check['amount']) > 0.01:
                        logger.info(f"Re-analysis found different amount, updating matches...")
                        # Update check data with new analysis
                        for check in filtered_checks:
                            if check['check_id'] == match['check_id']:
                                check['amount'] = float(new_analysis['Amount']['Numerical'])
                                check['amount_confidence'] = new_analysis.get('Amount Confidence', 'UNKNOWN')
                        
                        # Get new matches with updated data
                        request['checks'] = filtered_checks
                        matches = await nova_pro.match_data(request)
                        logger.debug(f"Nova Pro response: {matches}")
                        try:
                            # Extract JSON from markdown response
                            json_blocks = matches.split("```json")
                            if len(json_blocks) > 1:
                                # Take the last JSON block
                                json_text = json_blocks[-1].split("```")[0].strip()
                                logger.debug(f"Extracted JSON: {json_text}")
                                matches_data = json.loads(json_text)
                            else:
                                # Try parsing the whole response as JSON
                                matches_data = json.loads(matches)
                        except json.JSONDecodeError as e:
                            logger.error(f"Failed to parse Nova Pro response: {str(e)}")
                            logger.error(f"Response content: {matches}")
                            raise
                        break
    
    return matches_data

def format_matches_output(matches_data: Dict) -> Dict:
    """Format the matches data for better readability"""
    formatted_output = {
        "check_analysis": [],
        "payment_matches": []
    }
    
    # Parse and format matches
    matches_data = json.loads(matches_data.strip('```json\n').strip('```'))
    for match in matches_data:
        formatted_match = {
            "Check Details": {
                "Check Number": match['check_number'],
                "Amount": f"${match['amount']:,.2f}",
                "Date": match['date'],
                "Payee": match['payee']
            },
            "Matching Invoices": []
        }
        
        for invoice in match.get('matching_invoices', []):
            formatted_invoice = {
                "Invoice Number": invoice['invoice_number'],
                "Amount": f"${invoice['amount']:,.2f}",
                "Date": invoice['date'],
                "Payee": invoice['payee'],
                "Match Details": {
                    "Discrepancy": invoice['discrepancy'],
                    "Confidence": invoice['confidence_level']
                }
            }
            formatted_match["Matching Invoices"].append(formatted_invoice)
        
        formatted_output["payment_matches"].append(formatted_match)
    
    return formatted_output

async def process_input_folder(folder_path: str) -> Dict:
    """Process all files in the input folder"""
    try:
        # Initialize Nova client
        logger.info("Initializing Nova client...")
        nova = NovaClient()
        await nova.initialize()
        nova_pro = nova.nova_pro_client
        nova_lite = nova.nova_lite_client
        
        # Get bank statement
        bank_data_str = ""
        bank_files = glob.glob(os.path.join(folder_path, "*.csv"))
        if bank_files:
            bank_file = bank_files[0]
            logger.info(f"Found bank statement: {bank_file}")
            with open(bank_file, 'r') as f:
                bank_data_str = f.read()
        
        # Get check PDFs
        check_files = glob.glob(os.path.join(folder_path, "*.pdf"))
        if not check_files:
            logger.error("No check PDFs found")
            return
            
        logger.info(f"Found {len(check_files)} check PDFs")
        
        # Process each check
        check_results = []
        for pdf_path in check_files:
            check_result = await analyze_check_image(nova_lite, pdf_path)
            if check_result:
                check_results.append(check_result)
        
        if not check_results:
            logger.error("No valid check results")
            return
            
        # Get billing data from Knack
        logger.info("Getting billing data from Knack...")
        knack = KnackClient()
        invoice_data = await knack.get_unpaid_approved_billings()
        if not invoice_data:
            logger.error("No invoice data found")
            return
            
        logger.info(f"Got {len(invoice_data)} invoices from Knack")
        
        # Match checks with invoices
        logger.info("Starting match with Nova Pro...")
        matches = await match_checks_with_invoices(nova_pro, nova_lite, check_results, invoice_data, bank_data_str)
        if not matches:
            logger.error("Failed to get matches from Nova Pro")
            return
            
        logger.info("Successfully got matches from Nova Pro")
        
        # Format results for better readability
        formatted_output = format_matches_output(matches)
        
        # Save formatted results
        debug_file = os.path.join(folder_path, "payment_matching_results.json")
        with open(debug_file, 'w') as f:
            json.dump(formatted_output, f, indent=2)
            
        # Print summary to console
        logger.info("\n=== Payment Matching Results ===")
        for match in formatted_output["payment_matches"]:
            check = match["Check Details"]
            logger.info(f"\nCheck #{check['Check Number']} ({check['Amount']}):")
            logger.info(f"  From: {check['Payee']}")
            logger.info(f"  Date: {check['Date']}")
            
            logger.info("  Matching Invoices:")
            for invoice in match["Matching Invoices"]:
                logger.info(f"    - {invoice['Invoice Number']}: {invoice['Amount']} ({invoice['Date']}) - {invoice['Payee']}")
                logger.info(f"      {invoice['Match Details']['Discrepancy']} (Confidence: {invoice['Match Details']['Confidence']})")
        
        # Return results
        return {
            'check_results': check_results,
            'matches': matches
        }
        
    except Exception as e:
        logger.error(f"Error in process_input_folder: {str(e)}")
        raise

async def get_input_folder() -> str:
    """Get input folder path using GUI"""
    logger.info("Creating root window...")
    root = tk.Tk()
    root.withdraw()
    
    logger.info("Opening folder dialog...")
    folder_path = filedialog.askdirectory(
        title="Select Input Folder (containing PDFs, CSV, and JSON)"
    )
    
    root.destroy()
    return folder_path

async def main():
    """Main function to process payments"""
    try:
        # Initialize Nova clients
        nova_lite = NovaLiteClient()
        nova_pro = NovaProClient()
        await nova_lite.initialize()
        await nova_pro.initialize()
        
        # Get input folder from user
        root = tk.Tk()
        root.withdraw()
        folder_path = filedialog.askdirectory(title="Select folder containing PDFs and data files")
        if not folder_path:
            logger.error("No folder selected")
            return
            
        # Process all PDFs in the folder
        pdf_files = [f for f in os.listdir(folder_path) if f.endswith('.pdf')]
        check_results = []
        
        for pdf_file in pdf_files:
            pdf_path = os.path.join(folder_path, pdf_file)
            logger.info(f"Processing check: {pdf_file}")
            
            result = await analyze_check_image(nova_lite, pdf_path)
            if result:
                check_results.append(result)
        
        # Find and load Knack billing download data
        billing_files = [f for f in os.listdir(folder_path) if f.startswith('billing_download') and f.endswith('.json')]
        if not billing_files:
            logger.error("No billing_download*.json file found in the selected folder")
            return
            
        if len(billing_files) > 1:
            logger.warning(f"Multiple billing download files found: {billing_files}. Using the most recent one.")
            # Sort by modification time, newest first
            billing_files.sort(key=lambda x: os.path.getmtime(os.path.join(folder_path, x)), reverse=True)
            
        billing_file = os.path.join(folder_path, billing_files[0])
        logger.info(f"Using Knack billing data from: {billing_files[0]}")
        
        with open(billing_file, 'r') as f:
            invoice_data = json.load(f)
            
        # Save parsed invoice data for debugging
        parsed_invoices = []
        for invoice in invoice_data:
            try:
                # Extract amount from field_2349 (e.g. "$5,500.00")
                amount_str = invoice.get('field_2349', '0').replace('$', '').replace(',', '')
                amount = float(amount_str)
                
                # Get payee name from field_1350 (removing HTML tags)
                payee = invoice.get('field_1350', '').replace('<span class="', '').split('">')[1].split('</span>')[0]
                
                parsed_invoice = {
                    'invoice_number': invoice.get('field_1418', ''),
                    'amount': amount,
                    'date': invoice.get('field_1351', ''),
                    'payee': payee,
                    'resident_name': invoice.get('field_2540', ''),  # Adding resident name field
                    'raw_payee': invoice.get('field_1350', '')  # Adding raw payee field for debugging
                }
                parsed_invoices.append(parsed_invoice)
            except Exception as e:
                logger.error(f"Error parsing invoice data: {str(e)}")
                continue
                
        # Save parsed data for debugging
        debug_data = {
            'check_results': check_results,
            'parsed_invoices': parsed_invoices
        }
        
        debug_file = os.path.join(folder_path, "parsed_data_debug.json")
        with open(debug_file, 'w') as f:
            json.dump(debug_data, f, indent=2)
        logger.info(f"Saved parsed data for debugging to: {debug_file}")
            
        # Find and load bank data
        bank_files = [f for f in os.listdir(folder_path) 
                     if (f.startswith('stmt') or f.startswith('bank_data')) and f.endswith('.csv')]
        if not bank_files:
            logger.error("No bank statement CSV file found (should start with 'stmt' or 'bank_data')")
            return
            
        if len(bank_files) > 1:
            logger.warning(f"Multiple bank files found: {bank_files}. Using the most recent one.")
            # Sort by modification time, newest first
            bank_files.sort(key=lambda x: os.path.getmtime(os.path.join(folder_path, x)), reverse=True)
            
        bank_file = os.path.join(folder_path, bank_files[0])
        logger.info(f"Using bank data from: {bank_files[0]}")
        
        with open(bank_file, 'r') as f:
            bank_data_str = f.read()
        
        # Match checks with invoices
        logger.info("Starting match with Nova Pro...")
        matches = await match_checks_with_invoices(nova_pro, nova_lite, check_results, invoice_data, bank_data_str)
        if not matches:
            logger.error("Failed to get matches from Nova Pro")
            return
            
        logger.info("Successfully got matches from Nova Pro")
        
        # Format results for output
        output = {
            "check_analysis": [],
            "payment_matches": []
        }
        
        # Format check results
        for check in check_results:
            formatted_check = {
                "Check Number": check['check_number'],
                "Amount": f"${check['amount']:,.2f}",
                "Date": check['date'],
                "Payee": check['payee'],
                "Drawer": check['drawer'],
                "Written Amount": check['written_amount'],
                "Needs Review": "Yes" if check['needs_review'] else "No",
                "File": Path(check['pdf_path']).name
            }
            output["check_analysis"].append(formatted_check)
        
        # Parse and format matches
        matches_data = json.loads(matches.strip('```json\n').strip('```'))
        for match in matches_data:
            formatted_match = {
                "Check Details": {
                    "Check Number": match['check_number'],
                    "Amount": f"${match['amount']:,.2f}",
                    "Date": match['date'],
                    "Payee": match['payee']
                },
                "Matching Invoices": []
            }
            
            for invoice in match.get('matching_invoices', []):
                formatted_invoice = {
                    "Invoice Number": invoice['invoice_number'],
                    "Amount": f"${invoice['amount']:,.2f}",
                    "Date": invoice['date'],
                    "Payee": invoice['payee'],
                    "Match Details": {
                        "Discrepancy": invoice['discrepancy'],
                        "Confidence": invoice['confidence_level']
                    }
                }
                formatted_match["Matching Invoices"].append(formatted_invoice)
            
            output["payment_matches"].append(formatted_match)
            
        # Save formatted results
        debug_file = os.path.join(folder_path, "payment_matching_results.json")
        with open(debug_file, 'w') as f:
            json.dump(output, f, indent=2)
            
        # Print summary to console
        logger.info("\n=== Check Analysis ===")
        for check in output["check_analysis"]:
            logger.info(f"\nCheck #{check['Check Number']}:")
            logger.info(f"  Amount: {check['Amount']}")
            logger.info(f"  Date: {check['Date']}")
            logger.info(f"  Payee: {check['Payee']}")
            logger.info(f"  Drawer: {check['Drawer']}")
            
        logger.info("\n=== Payment Matches ===")
        for match in output["payment_matches"]:
            check = match["Check Details"]
            logger.info(f"\nCheck #{check['Check Number']} (${float(check['Amount'].replace('$', '').replace(',', '')):,.2f}):")
            logger.info(f"  From: {check['Payee']}")
            logger.info(f"  Date: {check['Date']}")
            
            logger.info("  Matching Invoices:")
            for invoice in match["Matching Invoices"]:
                logger.info(f"    - {invoice['Invoice Number']}: {invoice['Amount']} ({invoice['Date']}) - {invoice['Payee']}")
                logger.info(f"      {invoice['Match Details']['Discrepancy']} (Confidence: {invoice['Match Details']['Confidence']})")
        
        # Save results
        results = {
            'check_results': check_results,
            'matches': matches
        }
        
        output_file = os.path.join(folder_path, "results.json")
        with open(output_file, 'w') as f:
            json.dump(results, f, indent=2)
            
        logger.info(f"Results saved to: {output_file}")
        
    except Exception as e:
        logger.error(f"Error in main: {str(e)}", exc_info=True)

if __name__ == "__main__":
    asyncio.run(main())
