import boto3
import base64
import json
from typing import Dict, Optional
import logging
import os
import time
import asyncio
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

class NovaBaseClient:
    def __init__(self):
        load_dotenv()
        self.bedrock = None
        self.runtime = None
        
    async def initialize(self):
        """Initialize AWS clients asynchronously"""
        if self.runtime is not None:
            return
            
        try:
            # Create STS client
            sts_client = boto3.client('sts')
            
            # Assume role for Bedrock access
            role = sts_client.assume_role(
                RoleArn='arn:aws:iam::664604937404:role/BedrockAccessRole',
                RoleSessionName='BedrockSession'
            )
            
            # Get temporary credentials
            credentials = role['Credentials']
            
            # Create Bedrock clients with assumed role credentials
            self.bedrock = boto3.client(
                'bedrock',
                aws_access_key_id=credentials['AccessKeyId'],
                aws_secret_access_key=credentials['SecretAccessKey'],
                aws_session_token=credentials['SessionToken'],
                region_name='us-west-2'
            )
            
            self.runtime = boto3.client(
                'bedrock-runtime',
                aws_access_key_id=credentials['AccessKeyId'],
                aws_secret_access_key=credentials['SecretAccessKey'],
                aws_session_token=credentials['SessionToken'],
                region_name='us-west-2'
            )
            
            logger.debug("AWS clients initialized with assumed role")
            
        except Exception as e:
            logger.error(f"Error initializing AWS clients: {str(e)}")
            raise

class NovaLiteClient(NovaBaseClient):
    MODEL_ID = "us.amazon.nova-lite-v1:0"
    
    def __init__(self):
        super().__init__()
        
    async def analyze_check_image(self, request: Dict) -> str:
        """Analyze a check image using Nova Lite"""
        try:
            # First attempt - basic analysis
            response = self.runtime.invoke_model(
                modelId=self.MODEL_ID,
                body=json.dumps({
                    **request,
                    "instructions": """
                    Please analyze this check image with extra attention to accuracy:
                    1. Compare the numerical amount with the written amount for consistency
                    2. If they don't match, carefully recheck both amounts
                    3. Extract full names without any numerical identifiers
                    4. Pay special attention to handwriting variations
                    
                    Return a JSON object with:
                    - Payee Name
                    - Amount (both numerical and written)
                    - Date
                    - Check Number
                    - Drawer/Account Holder Name
                    - Amount Confidence: HIGH if numerical and written amounts match, LOW if they don't
                    - Additional Review Required: Yes if amounts don't match or other issues found
                    """
                })
            )
            
            if response:
                model_response = json.loads(response["body"].read())
                result = json.loads(model_response['output']['message']['content'][0]['text'].strip('```json\n').strip('```'))
                
                # If amounts don't match or confidence is low, try a second analysis
                if result.get('Amount Confidence') == 'LOW':
                    logger.info("Amount mismatch detected, performing second analysis...")
                    response = self.runtime.invoke_model(
                        modelId=self.MODEL_ID,
                        body=json.dumps({
                            **request,
                            "instructions": f"""
                            Please carefully reanalyze this check image, focusing specifically on the amount.
                            The first analysis found:
                            - Numerical amount: {result['Amount']['Numerical']}
                            - Written amount: {result['Amount']['Written']}
                            
                            Please verify:
                            1. Look for any smudges or unclear digits in the numerical amount
                            2. Carefully parse the written amount word by word
                            3. Check for any corrections or strike-throughs
                            4. Consider common writing variations (e.g., 'forty' vs 'fourty')
                            
                            Return the same JSON format with your highest confidence analysis.
                            """
                        })
                    )
                    
                    if response:
                        second_response = json.loads(response["body"].read())
                        second_result = json.loads(second_response['output']['message']['content'][0]['text'].strip('```json\n').strip('```'))
                        
                        # Use the result with higher confidence
                        if second_result.get('Amount Confidence') == 'HIGH':
                            result = second_result
                
                return json.dumps(result, indent=2)
                
        except Exception as e:
            logger.error(f"Error in analyze_check_image: {str(e)}")
            raise

class NovaProClient(NovaBaseClient):
    MODEL_ID = "us.amazon.nova-pro-v1:0"
    
    def __init__(self):
        super().__init__()
        
    async def match_data(self, request: Dict) -> str:
        """Match data using Nova Pro"""
        try:
            logger.debug(f"Sending request to Nova Pro with model ID: {self.MODEL_ID}")
            
            # Format the data for Nova Pro
            checks_str = json.dumps(request['checks'], indent=2)
            invoices_str = json.dumps(request['invoices'], indent=2)
            bank_data_str = request.get('bank_data', '')
            
            # Create system prompt for consistent matching behavior
            system = [{
                "text": """You are an expert at matching payment data. Follow these rules:
                1. Name Matching: Compare first/last names, consider variations (e.g. Bob/Robert)
                2. Amount Matching: Exact matches are HIGH confidence, within $50 is MEDIUM
                3. Date Matching: Same month increases confidence, >1 month apart decreases it
                4. Flag close matches (within $50) for manual review"""
            }]
            
            # Create messages for the request
            messages = [{
                "role": "user",
                "content": [
                    {
                        "text": f"""Match these payments and return ONLY a JSON array of matches:

1. Check Data:
{checks_str}

2. Invoice Data:
{invoices_str}

3. Bank Transaction Data:
{bank_data_str}

Format: [
  {{
    "check": {{...}},
    "invoice": {{...}},
    "bank_transaction": {{...}},
    "match_confidence": "HIGH|MEDIUM|LOW",
    "notes": "any relevant notes"
  }}
]"""
                    }
                ]
            }]
            
            # Set inference parameters
            inference_config = {
                "maxTokens": 2000,
                "temperature": 0.1,
                "topP": 0.9
            }
            
            logger.debug("Request size: %d bytes", len(json.dumps(messages)))
            response = self.runtime.converse(
                modelId=self.MODEL_ID,
                messages=messages,
                system=system,
                inferenceConfig=inference_config
            )
            
            if response:
                logger.debug("Got response from Nova Pro")
                logger.debug(f"Response: {json.dumps(response, indent=2)}")
                return response["output"]["message"]["content"][0]["text"]
                
        except Exception as e:
            logger.error(f"Error in match_data: {str(e)}")
            raise

class NovaClient:
    # Nova Pro profile ARN
    NOVA_PRO_PROFILE = "us.amazon.nova-pro-v1:0"
    
    def __init__(self):
        """Initialize the Nova client"""
        self.bedrock = None
        self.runtime = None
        self.nova_pro_client = NovaProClient()
        self.nova_lite_client = NovaLiteClient()
    
    async def initialize(self):
        """Initialize AWS clients asynchronously"""
        if self.bedrock is not None:
            return
            
        try:
            # Create STS client
            sts_client = boto3.client('sts')
            
            # Assume role for Bedrock access
            role = sts_client.assume_role(
                RoleArn='arn:aws:iam::664604937404:role/BedrockAccessRole',
                RoleSessionName='BedrockSession'
            )
            
            # Get temporary credentials
            credentials = role['Credentials']
            
            # Create Bedrock client with assumed role credentials
            self.bedrock = boto3.client(
                'bedrock',
                aws_access_key_id=credentials['AccessKeyId'],
                aws_secret_access_key=credentials['SecretAccessKey'],
                aws_session_token=credentials['SessionToken'],
                region_name='us-west-2'
            )
            
            # Create Bedrock Runtime client
            self.runtime = boto3.client(
                'bedrock-runtime',
                aws_access_key_id=credentials['AccessKeyId'],
                aws_secret_access_key=credentials['SecretAccessKey'],
                aws_session_token=credentials['SessionToken'],
                region_name='us-west-2'
            )
            
            await self.nova_pro_client.initialize()
            await self.nova_lite_client.initialize()
            
            logger.debug("AWS clients initialized successfully")
            
        except Exception as e:
            logger.error(f"Error initializing AWS clients: {e}")
            raise

    async def analyze_check_image(self, check_id: str, image_b64: str) -> Dict:
        """
        Analyze a check image using Nova Pro
        Args:
            check_id: Unique identifier for the check
            image_b64: Base64 encoded check image
        Returns:
            Dictionary containing analysis results
        """
        await self.initialize()  # Ensure clients are initialized
        try:
            # Create request body
            request_body = {
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "text": "Please analyze this check image and extract the following information: payee name, amount, date, memo line, and check number.\n\n[Image Data: " + image_b64 + "]"
                            }
                        ]
                    }
                ]
            }
            
            # Make synchronous call
            response = await self.nova_pro_client.match_data(request_body)
            
            try:
                # Parse the content into our expected format
                content = response
                parsed_result = {
                    'confidence_score': 0.9,  # Default high confidence for now
                    'content': content
                }
                
                return parsed_result
                
            except Exception as e:
                logger.error(f"Error parsing Nova Pro response for {check_id}: {e}")
                return {
                    'error': f"Failed to parse Nova Pro response: {e}",
                    'confidence_score': 0
                }
            
        except Exception as e:
            error_msg = f"Error calling Nova Pro API for {check_id}: {e}"
            logger.error(error_msg)
            return {
                'error': str(e),
                'confidence_score': 0
            }

    async def analyze_documents(self, statement_path: str, checks_folder: str, billing_json: str) -> str:
        """
        Analyze documents and match payments to invoices
        Args:
            statement_path: Path to bank statement file
            checks_folder: Path to folder containing check images
            billing_json: Path to billing data JSON file
        Returns:
            CSV string with payment matches
        """
        await self.initialize()  # Ensure clients are initialized
        try:
            # Load statement data
            with open(statement_path, 'r') as f:
                statement_data = f.read()
                
            # Load billing data
            with open(billing_json, 'r') as f:
                billing_data = json.load(f)
                
            # Create request body
            request_body = {
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "text": statement_data
                            }
                        ]
                    },
                    {
                        "role": "assistant",
                        "content": [
                            {
                                "text": "I'll help analyze the bank statement and match payments."
                            }
                        ]
                    },
                    {
                        "role": "user",
                        "content": [
                            {
                                "text": f"Please analyze the bank statement and billing data to match payments to invoices.\n\nBilling Data:\n{json.dumps(billing_data, indent=2)}\n\nPlease provide a CSV with the following columns:\nInvoice Number,Invoice Amount,Resident Name,Payment Amount,Deposit Date,Needs Review"
                            }
                        ]
                    }
                ]
            }
            
            # Send analysis request
            response = await self.nova_pro_client.match_data(request_body)
            
            # Return CSV content
            return response
            
        except Exception as e:
            logger.error(f"Error analyzing documents: {str(e)}")
            raise
