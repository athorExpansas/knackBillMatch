from datetime import datetime, timedelta
from .knack_client import KnackClient
from .financial_clients import BankOfAmericaClient, BillDotComClient, WellsFargoClient
from .matcher import BillingMatcher
from .report_generator import ReportGenerator

def main():
    # Initialize clients
    knack_client = KnackClient()
    financial_clients = [
        BankOfAmericaClient(),
        BillDotComClient(),
        WellsFargoClient()
    ]
    
    # Initialize matcher and report generator
    matcher = BillingMatcher(financial_clients)
    report_generator = ReportGenerator()
    
    # Get unbilled records from Knack
    knack_records = knack_client.get_unbilled_records()
    
    if not knack_records:
        print("No unbilled records found in Knack")
        return
    
    # Set date range for transaction search (last 30 days)
    end_date = datetime.now()
    start_date = end_date - timedelta(days=30)
    
    # Find matches
    print(f"Searching for matches in {len(knack_records)} records...")
    matches = matcher.find_matches(knack_records, start_date, end_date)
    
    if not matches:
        print("No matches found")
        return
    
    # Generate report
    print(f"Generating report for {len(matches)} matches...")
    report_path = report_generator.generate_report(matches)
    print(f"Report generated: {report_path}")
    
    # Update Knack records after verification
    print("Please review the report and confirm to update Knack records (y/n)")
    confirmation = input().lower()
    
    if confirmation == 'y':
        print("Updating Knack records...")
        for match in matches:
            knack_client.update_record_status(
                match['knack_record']['id'],
                {
                    'date': match['transaction']['date'],
                    'amount': match['transaction']['amount'],
                    'reference': match['transaction']['id'],
                    'method': 'check'
                }
            )
        print("Knack records updated successfully")
    else:
        print("Update cancelled")

if __name__ == "__main__":
    main()
