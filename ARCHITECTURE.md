# KnackBillingMatch Architecture

This document outlines the architecture of the KnackBillingMatch system, which automates the matching of check payments with Knack billing invoices using AI-powered check processing.

## System Overview

The system processes check images and matches them with billing invoices using the following pipeline:

1. Check Image Processing
2. Data Extraction using Llama AI
3. Invoice Data Processing
4. Payment Matching Logic

## Key Components

### 1. Check Processing (`process_payments_llama.py`)

The main script that orchestrates the entire matching process:

```
process_input_folder/
├── Convert PDF to PNG (300 DPI)
├── Analyze Check with Consensus
│   ├── Multiple Llama API Calls
│   └── Consensus Building
├── Load Invoice Data
└── Match Checks with Invoices
```

Key Features:
- High-resolution PDF to PNG conversion (300 DPI)
- Consensus-based check analysis for reliability
- Fuzzy matching with configurable weights
- Detailed logging for debugging

### 2. Llama Client (`llama_client.py`)

Handles communication with the Llama API for check data extraction:

```python
class LlamaClient:
    - extract_check_info()  # Main extraction method
    - _make_request()       # API communication
```

Features:
- Strict JSON response formatting
- Error handling and retries
- Base64 image encoding
- Optimized prompting for accurate extraction

### 3. Data Models

#### Check Data Structure:
```json
{
    "check_number": "string (3-4 digits)",
    "amount": "string ($X,XXX.XX)",
    "date": "string (MM/DD/YYYY)",
    "payee": "string",
    "from": "string",
    "from_address": "string",
    "memo": "string",
    "bank_name": "string"
}
```

#### Invoice Data Structure:
```json
{
    "invoice_number": "string",
    "amount": "string",
    "date": "string",
    "payee": "string",
    "resident_name": "string",
    "raw_payee": "string"
}
```

### 4. Matching Logic

The system uses a weighted scoring system to match checks with invoices:

```python
Weights:
- Amount: 40%  (exact match required)
- Name: 30%    (fuzzy matching with word overlap)
- Date: 20%    (proximity-based scoring)
- Payee: 10%   (fuzzy matching)

Match Threshold: 0.70 (70% confidence)
```

#### Name Matching Features:
- Unit number removal (e.g., "Kurt Elliott 413" → "Kurt Elliott")
- Word-based overlap scoring
- Case-insensitive comparison
- Punctuation normalization
- Word order independence

## File Structure

```
KnackBillingMatch/
├── scripts/
│   ├── process_payments_llama.py  # Main processing script
│   ├── process_payments.py        # Legacy processing
│   └── test_matching.py          # Test suite
├── src/
│   └── llama_client.py           # Llama API client
├── logs/                         # Detailed processing logs
├── .env                          # Configuration
└── .env.example                  # Configuration template
```

## Configuration

Required environment variables:
- `LLAMA_API_BASE_URL`: Llama API endpoint
- `LLAMA_API_MODEL`: Model name for check processing
- Other configuration as specified in `.env.example`

## Best Practices

1. **Check Processing**:
   - Always use consensus from multiple API calls
   - Convert PDFs once at high resolution
   - Cache intermediate results

2. **Matching**:
   - Use fuzzy matching for names
   - Require exact amount matches
   - Consider date proximity
   - Weight different criteria appropriately

3. **Error Handling**:
   - Detailed logging at each step
   - Graceful fallbacks for API failures
   - Data validation before processing

## Common Issues and Solutions

1. **JSON Parsing**:
   - Problem: Llama may return markdown-formatted or explanatory text
   - Solution: Extract JSON using regex and strict parsing

2. **Name Matching**:
   - Problem: Different name formats and unit numbers
   - Solution: Normalize names and use word overlap scoring

3. **Date Matching**:
   - Problem: Dates may be close but not exact
   - Solution: Use date proximity scoring

## Future Improvements

1. **Performance**:
   - Batch processing for multiple checks
   - Parallel API calls
   - Response caching

2. **Accuracy**:
   - Fine-tune Llama model for check processing
   - Add more validation rules
   - Expand matching criteria

3. **User Interface**:
   - Add web interface for manual review
   - Real-time processing status
   - Match confidence visualization

## Deployment

1. Clone repository
2. Copy `.env.example` to `.env` and configure
3. Install dependencies
4. Run `process_payments_llama.py`

## Monitoring

The system provides detailed logs in the `logs/` directory with:
- Processing steps
- API responses
- Match scores
- Errors and warnings

Monitor these logs to track system performance and identify issues.
