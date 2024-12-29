# Knack Billing Match

A Python application that automates the process of matching billing records between Knack database and various financial sources (Bank of America, Bill.com, Wells Fargo). The system uses Amazon Nova for check image interpretation and verification.

## Features
- Fetches billing records from Knack database
- Checks multiple financial sources for payment matches
- Uses Amazon Nova for check image verification
- Generates verification reports with matched transactions
- Updates Knack records after verification
- Prevents duplicate matching of transactions

## Setup
1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Configure environment variables in `.env`:
```
KNACK_APP_ID=your_app_id
KNACK_API_KEY=your_api_key
PLAID_CLIENT_ID=your_client_id
PLAID_SECRET=your_secret
BOFA_API_KEY=your_key
BILLDOTCOM_API_KEY=your_key
WELLS_FARGO_API_KEY=your_key
AWS_ACCESS_KEY_ID=your_aws_key
AWS_SECRET_ACCESS_KEY=your_aws_secret
```

## Usage
Run the main script:
```bash
python main.py
```

The script will:
1. Fetch unbilled records from Knack
2. Check financial sources for matches
3. Generate a verification report
4. Update Knack records after verification

## Report Generation
Reports are generated in the `reports` directory with:
- Transaction details
- Check images
- Invoice information
- Match confidence scores
