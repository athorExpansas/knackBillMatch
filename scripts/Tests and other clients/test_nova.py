import boto3
import json
import os
from botocore.exceptions import ClientError
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Nova Pro inference profile
NOVA_PRO_PROFILE = "arn:aws:bedrock:us-west-2:664604937404:inference-profile/us.amazon.nova-pro-v1:0"

def get_bedrock_clients():
    # Create STS client
    sts_client = boto3.client(
        'sts',
        aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
        aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
        region_name=os.getenv('AWS_REGION')
    )
    
    try:
        print("Getting temporary credentials via STS...")
        role_arn = "arn:aws:iam::664604937404:role/BedrockAccessRole"
        
        assumed_role = sts_client.assume_role(
            RoleArn=role_arn,
            RoleSessionName="BedrockSession"
        )
        
        # Get temporary credentials
        credentials = assumed_role['Credentials']
        print("Successfully obtained temporary credentials")
        
        # Create Bedrock clients with temporary credentials
        bedrock = boto3.client(
            'bedrock',
            aws_access_key_id=credentials['AccessKeyId'],
            aws_secret_access_key=credentials['SecretAccessKey'],
            aws_session_token=credentials['SessionToken'],
            region_name=os.getenv('AWS_REGION')
        )
        
        runtime = boto3.client(
            'bedrock-runtime',
            aws_access_key_id=credentials['AccessKeyId'],
            aws_secret_access_key=credentials['SecretAccessKey'],
            aws_session_token=credentials['SessionToken'],
            region_name=os.getenv('AWS_REGION')
        )
        
        return bedrock, runtime
        
    except ClientError as e:
        print(f"Error assuming role: {str(e)}")
        if 'Message' in e.response['Error']:
            print(f"Error Message: {e.response['Error']['Message']}")
        raise

def test_nova():
    print("Testing Bedrock connectivity...")
    print(f"Using region: {os.getenv('AWS_REGION')}")
    
    try:
        # Get clients with temporary credentials
        bedrock, runtime = get_bedrock_clients()
        
        # List available models
        print("\nListing available models...")
        response = bedrock.list_foundation_models()
        models = response.get('modelSummaries', [])
        
        print("\nAvailable Nova models:")
        for model in models:
            model_id = model.get('modelId')
            if 'nova' in model_id.lower():
                print(f"- {model_id}: {model.get('modelName')} (Customizations: {model.get('customizationsSupported', [])})")
        
        # Check Nova Pro access
        print("\nChecking Nova Pro access...")
        model_info = bedrock.get_foundation_model(
            modelIdentifier='amazon.nova-pro-v1:0'
        )
        print(f"Nova Pro model info: {json.dumps(model_info, indent=2)}")
        
        # Test Nova Pro inference
        print("\nTesting Nova Pro inference using profile:", NOVA_PRO_PROFILE)
        response = runtime.invoke_model(
            modelId=NOVA_PRO_PROFILE,  # Use the inference profile instead of base model
            contentType='application/json',
            accept='application/json',
            body=json.dumps({
                "inferenceConfig": {
                    "max_new_tokens": 1000
                },
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "text": "Say hello!"
                            }
                        ]
                    }
                ]
            })
        )
        
        result = json.loads(response.get('body').read())
        print("Response:", result)
        print("\nSuccess! Connection to Bedrock is working.")
        
    except ClientError as e:
        print(f"\nAWS Error:")
        error_code = e.response.get('Error', {}).get('Code', 'Unknown')
        error_message = e.response.get('Error', {}).get('Message', 'No message')
        print(f"Error Code: {error_code}")
        print(f"Error Message: {error_message}")
        print(f"Full error response: {json.dumps(e.response, indent=2)}")
        
        if error_code == 'AccessDeniedException':
            print("\nPermission troubleshooting steps:")
            print("1. Verify BedrockAccessRole has AmazonBedrockFullAccess policy")
            print("2. Verify BedrockAccessRole trust relationship allows bedrockExternal user to assume it")
            print("3. Check if Nova Pro is enabled in the Bedrock console")
            print("4. Ensure you've accepted the model terms in AWS Marketplace")
        elif error_code == 'ValidationException':
            print("\nValidation error troubleshooting:")
            print("1. Verify the inference profile ARN is correct")
            print("2. Make sure the inference profile is active")
            print("3. Check if the request format matches Nova Pro's requirements")
        
    except Exception as e:
        print(f"Other error: {str(e)}")

if __name__ == "__main__":
    test_nova()
