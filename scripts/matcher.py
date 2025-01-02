from typing import List, Dict, Tuple
from scripts.process_payments_llama import match_checks_with_invoices as llama_match

def match_payments(check_data: List[Dict], billing_data: List[Dict]) -> List[Dict]:
    """
    Match payments with billing data using the Llama-based matching logic.
    
    Args:
        check_data: List of processed check data
        billing_data: List of billing records
        
    Returns:
        List of potential matches for each check
    """
    matches, _, _ = llama_match(check_data, billing_data)
    return matches
