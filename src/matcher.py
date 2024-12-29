from typing import List, Dict, Set
from datetime import datetime
from .nova_client import NovaClient
from .financial_clients import FinancialClient

class BillingMatcher:
    def __init__(self, financial_clients: List[FinancialClient]):
        self.financial_clients = financial_clients
        self.nova_client = NovaClient()
        self.matched_transactions: Set[str] = set()
    
    def find_matches(self, knack_records: List[Dict], start_date: datetime, end_date: datetime) -> List[Dict]:
        """
        Find matches between Knack records and financial transactions
        Args:
            knack_records: List of unbilled records from Knack
            start_date: Start date for transaction search
            end_date: End date for transaction search
        Returns:
            List of matched records with confidence scores
        """
        matches = []
        
        # Get transactions from all financial sources
        all_transactions = []
        for client in self.financial_clients:
            transactions = client.get_transactions(start_date, end_date)
            all_transactions.extend(transactions)
        
        # Find matches for each Knack record
        for record in knack_records:
            record_matches = self._find_record_matches(record, all_transactions)
            matches.extend(record_matches)
        
        return matches
    
    def _find_record_matches(self, record: Dict, transactions: List[Dict]) -> List[Dict]:
        """
        Find matches for a single Knack record
        Args:
            record: Single Knack record
            transactions: List of financial transactions
        Returns:
            List of potential matches with confidence scores
        """
        matches = []
        
        for transaction in transactions:
            # Skip if transaction already matched
            if transaction['id'] in self.matched_transactions:
                continue
            
            # Check if amounts match
            if self._amounts_match(record['amount'], transaction['amount']):
                # Get check image if available
                check_image = self._get_check_image(transaction)
                
                if check_image:
                    # Analyze check image with Nova
                    nova_analysis = self.nova_client.analyze_check_image(check_image)
                    
                    if self._verify_match(record, transaction, nova_analysis):
                        matches.append({
                            'knack_record': record,
                            'transaction': transaction,
                            'check_image': check_image,
                            'nova_analysis': nova_analysis,
                            'confidence_score': nova_analysis['confidence_score']
                        })
                        self.matched_transactions.add(transaction['id'])
        
        return matches
    
    def _amounts_match(self, record_amount: float, transaction_amount: float) -> bool:
        """Check if amounts match within a small tolerance"""
        return abs(record_amount - transaction_amount) < 0.01
    
    def _get_check_image(self, transaction: Dict) -> bytes:
        """Get check image for a transaction if available"""
        try:
            client = self._get_client_for_transaction(transaction)
            return client.get_check_image(transaction['id'])
        except Exception:
            return None
    
    def _get_client_for_transaction(self, transaction: Dict) -> FinancialClient:
        """Get the appropriate financial client for a transaction"""
        # TODO: Implement logic to determine which client to use based on transaction
        return self.financial_clients[0]
    
    def _verify_match(self, record: Dict, transaction: Dict, nova_analysis: Dict) -> bool:
        """Verify if a match is valid based on Nova analysis"""
        # TODO: Implement more sophisticated matching logic
        return nova_analysis['confidence_score'] > 0.95
