import os
from datetime import datetime
from typing import Dict, List
import json
from decimal import Decimal
from .logger import setup_logger

logger = setup_logger('check_processor')

class CheckProcessor:
    def __init__(self, base_dir: str = "check_images"):
        """Initialize the check processor with a base directory for saving images"""
        self.base_dir = base_dir
        os.makedirs(base_dir, exist_ok=True)
        logger.info(f"Initialized CheckProcessor with base directory: {base_dir}")
    
    def save_check_images(self, transaction: Dict, bank: str) -> List[Dict]:
        """
        Save check images to disk and update the transaction with file paths
        Args:
            transaction: Transaction dictionary containing check data
            bank: Bank identifier (e.g., 'bofa', 'wellsfargo')
        Returns:
            List of paths to saved images
        """
        if not transaction.get('has_check_images'):
            logger.info(f"No check images to save for transaction {transaction.get('transaction_id')}")
            return []
        
        saved_paths = []
        transaction_date = datetime.strptime(transaction['date'], '%Y-%m-%d')
        
        # Create directory structure: base_dir/bank/YYYY/MM/DD/transaction_id/
        dir_path = os.path.join(
            self.base_dir,
            bank,
            transaction_date.strftime('%Y'),
            transaction_date.strftime('%m'),
            transaction_date.strftime('%d'),
            transaction['transaction_id']
        )
        os.makedirs(dir_path, exist_ok=True)
        logger.info(f"Created directory structure: {dir_path}")
        
        # Save each check's images
        for check in transaction.get('checks', []):
            check_num = check.get('extracted_check_number', 
                        check.get('check_number', f"check_{check['check_index']}")
                    )
            
            # Save images
            check['image_paths'] = []
            for img in check.get('images', []):
                filename = f"{check_num}_{img['type']}.png"
                file_path = os.path.join(dir_path, filename)
                
                try:
                    with open(file_path, 'wb') as f:
                        f.write(img['data'])
                    
                    check['image_paths'].append(file_path)
                    saved_paths.append(file_path)
                    logger.info(f"Saved {img['type']} image for check {check_num} to {file_path}")
                    
                    # Remove binary data after saving
                    img['data'] = None
                    img['file_path'] = file_path
                except Exception as e:
                    logger.error(f"Error saving check image {filename}: {e}")
        
        return saved_paths

    def validate_check_amounts(self, transaction: Dict) -> Dict:
        """
        Validate that the sum of check amounts matches the transaction amount
        Args:
            transaction: Transaction dictionary containing check data
        Returns:
            Dictionary with validation results
        """
        if not transaction.get('has_check_images'):
            logger.info(f"No check images to validate amounts for transaction {transaction.get('transaction_id')}")
            return {'valid': True, 'reason': 'No check images to validate'}
        
        # Convert transaction amount to Decimal for precise comparison
        transaction_amount = Decimal(str(abs(transaction['amount'])))
        check_amounts = []
        
        # Sum extracted amounts from checks
        for check in transaction.get('checks', []):
            if check.get('extracted_amount'):
                try:
                    # Remove currency symbols and convert to Decimal
                    amount_str = str(check['extracted_amount']).replace('$', '').replace(',', '')
                    check_amounts.append(Decimal(amount_str))
                except (ValueError, TypeError, decimal.InvalidOperation) as e:
                    error_msg = f"Invalid amount format in check {check.get('check_index')}: {check.get('extracted_amount')}"
                    logger.error(error_msg)
                    return {'valid': False, 'reason': error_msg}
        
        if not check_amounts:
            logger.warning(f"No valid check amounts found for transaction {transaction.get('transaction_id')}")
            return {'valid': False, 'reason': 'No valid check amounts found'}
        
        total_check_amount = sum(check_amounts)
        
        # Allow for small rounding differences (within 1 cent)
        if abs(total_check_amount - transaction_amount) <= Decimal('0.01'):
            logger.info(f"Amount validation successful for transaction {transaction.get('transaction_id')}")
            return {'valid': True, 'total_check_amount': float(total_check_amount)}
        else:
            error_msg = f"Amount mismatch: transaction={float(transaction_amount)}, checks={float(total_check_amount)}"
            logger.warning(f"{error_msg} for transaction {transaction.get('transaction_id')}")
            return {
                'valid': False,
                'reason': error_msg,
                'difference': float(abs(total_check_amount - transaction_amount))
            }

    def validate_confidence_scores(self, transaction: Dict, min_confidence: float = 0.8) -> Dict:
        """
        Validate confidence scores for check analysis
        Args:
            transaction: Transaction dictionary containing check data
            min_confidence: Minimum acceptable confidence score
        Returns:
            Dictionary with validation results
        """
        if not transaction.get('has_check_images'):
            logger.info(f"No check images to validate confidence for transaction {transaction.get('transaction_id')}")
            return {'valid': True, 'reason': 'No check images to validate'}
        
        low_confidence_checks = []
        
        for check in transaction.get('checks', []):
            confidence = check.get('confidence_score', 0)
            if confidence < min_confidence:
                check_info = {
                    'check_index': check['check_index'],
                    'confidence': confidence,
                    'amount': check.get('extracted_amount'),
                    'check_number': check.get('extracted_check_number')
                }
                low_confidence_checks.append(check_info)
                logger.warning(
                    f"Low confidence score ({confidence}) for check {check.get('check_number', check['check_index'])} "
                    f"in transaction {transaction.get('transaction_id')}"
                )
        
        if low_confidence_checks:
            return {
                'valid': False,
                'reason': 'Low confidence scores detected',
                'low_confidence_checks': low_confidence_checks
            }
        
        logger.info(f"Confidence validation successful for transaction {transaction.get('transaction_id')}")
        return {'valid': True}
