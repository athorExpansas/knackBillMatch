import aiohttp
import base64
import logging
import re
from typing import Dict, Any, Optional
from pathlib import Path
import json

logger = logging.getLogger(__name__)

class LlamaClient:
    def __init__(self, host: str = "192.168.1.215", port: int = 11434):
        """Initialize the Llama client for interacting with Ollama API.
        
        Args:
            host: The host address where Ollama is running
            port: The port number for the Ollama API
        """
        self.base_url = f"http://{host}:{port}"
        self.vision_model = "llama3.2-vision:11b"
        self.text_model = "llama3.2:latest"  # Use Llama 3.2 for text
        
    async def _make_request(self, endpoint: str, data: Dict[str, Any]) -> Dict:
        """Make an async request to the Ollama API.
        
        Args:
            endpoint: API endpoint
            data: Request payload
            
        Returns:
            Dict containing the API response
        """
        logger.debug(f"Making request to {endpoint} with data: {json.dumps(data, indent=2)}")
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{self.base_url}/{endpoint}", json=data) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"API request failed ({response.status}): {error_text}")
                
                # Read the response as text since it's ndjson
                response_text = await response.text()
                logger.debug(f"Raw API response: {response_text}")
                
                # Take the last line as the final response
                last_response = response_text.strip().split('\n')[-1]
                try:
                    return json.loads(last_response)
                except json.JSONDecodeError as e:
                    raise Exception(f"Failed to parse response: {response_text}")

    async def analyze_image(self, image_path: Path, prompt: str) -> Dict:
        """Analyze an image using the vision model.
        
        Args:
            image_path: Path to the image file
            prompt: The prompt to guide the image analysis
            
        Returns:
            Dict containing the model's response
        """
        # Read and encode the image
        with open(image_path, "rb") as img_file:
            image_data = base64.b64encode(img_file.read()).decode()
        
        # Prepare the request payload
        data = {
            "model": self.vision_model,
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                    "images": [image_data]
                }
            ]
        }
        
        try:
            response = await self._make_request("api/chat", data)
            # Try to extract JSON from the response text
            try:
                response_text = response.get('message', {}).get('content', '')
                logger.debug(f"Raw response: {response_text}")
                # Find JSON-like content
                start_idx = response_text.find('{')
                end_idx = response_text.rfind('}') + 1
                if start_idx >= 0 and end_idx > start_idx:
                    json_str = response_text[start_idx:end_idx]
                    return json.loads(json_str)
                return {}
            except json.JSONDecodeError:
                logger.error(f"Failed to parse JSON from response: {response_text}")
                return {}
        except Exception as e:
            logger.error(f"Error analyzing image {image_path}: {str(e)}")
            raise

    async def process_text(self, prompt: str, system_prompt: Optional[str] = None) -> Dict:
        """Process text using the model."""
        data = {
            "model": self.text_model,
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "stream": False  # Disable streaming for now
        }
        
        if system_prompt:
            data["messages"].insert(0, {
                "role": "system",
                "content": system_prompt
            })
        
        try:
            response = await self._make_request("api/chat", data)
            response_text = response.get('message', {}).get('content', '')
            logger.debug(f"Raw response: {response_text}")
            
            # Try to parse the entire response as JSON first
            try:
                result = json.loads(response_text)
                if isinstance(result, dict) and 'matches' in result:
                    return result
            except json.JSONDecodeError:
                pass
                
            # If that fails, try to find JSON-like content
            matches = re.findall(r'\{[^}]+\}', response_text.replace('\n', ' '))
            for match in matches:
                try:
                    result = json.loads(match)
                    # If it parses as JSON and has expected fields, return it
                    if isinstance(result, dict) and 'matches' in result:
                        return result
                except json.JSONDecodeError:
                    continue
            
            return response_text
        except Exception as e:
            logger.error(f"Error processing text: {str(e)}")
            raise

    async def extract_check_info(self, image_path: Path) -> Optional[Dict]:
        """Extract information from a check image using the Llama API."""
        if not image_path.exists():
            logger.error(f"Image file not found: {image_path}")
            return None

        with open(image_path, "rb") as f:
            image_bytes = f.read()
            image_base64 = base64.b64encode(image_bytes).decode()

        prompt = """You are a check processing assistant. Your task is to analyze this check image and extract key information.

IMPORTANT: You must return ONLY a raw JSON object. Do not include any explanatory text, markdown formatting, or backticks.

Example of correct response format:
{
    "check_number": "1234",
    "amount": "$5,490.00",
    "date": "10/01/2024",
    "payee": "The Mapleton",
    "from": "John Smith",
    "from_address": "123 Main St",
    "memo": "For rent",
    "bank_name": "Bank of America"
}

Look in these specific locations:
1. Check number: TOP RIGHT corner (3-4 digit number, NOT account/routing numbers)
2. Amount: Numerical amount in dollars and cents
3. Date: Top right area (MM/DD/YYYY format)
4. Payee: After "Pay to the order of"
5. From: Top left corner name(s)
6. From Address: Top left corner below name
7. Memo: Bottom left corner
8. Bank Name: Top of check

CRITICAL: Your response must be ONLY the JSON object. No other text. No explanations. No markdown."""

        try:
            response = await self._make_request("api/generate", data={
                "model": self.vision_model,
                "prompt": prompt,
                "images": [image_base64],
                "stream": False,
                "options": {
                    "temperature": 0.2,
                    "num_predict": 1024
                }
            })

            if not response or not response.get('response'):
                return None

            # Try to extract just the JSON part
            response_text = response['response']
            
            # Try to find JSON object in the response
            try:
                # Find the first { and last }
                start = response_text.find('{')
                end = response_text.rfind('}')
                if start != -1 and end != -1:
                    json_str = response_text[start:end+1]
                    return json.loads(json_str)
                else:
                    logger.error("No JSON object found in response")
                    return None
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse JSON from response: {e}")
                return None

        except Exception as e:
            logger.error(f"Error calling Llama API: {e}")
            return None
