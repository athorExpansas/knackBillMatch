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

    async def extract_check_info(self, image_path: Path) -> Dict:
        """Extract information from a check image."""
        # Read and encode the image
        with open(image_path, "rb") as img_file:
            image_data = base64.b64encode(img_file.read()).decode()
        
        prompt = """Analyze this check image and extract ALL of the following information:

1. Check number:
   - Look in the TOP RIGHT corner of the check
   - This is usually a 3-4 digit number
   - Do NOT use the account number from the bottom MICR line
   - Do NOT use any routing numbers
   - Only return the actual check number from top right

2. Amount:
   - Look for both numerical and written form
   - Use the numerical amount in dollars and cents

3. Date:
   - Usually in top right area
   - Format as MM/DD/YYYY

4. Payee:
   - Look for "Pay to the order of"
   - Get the full payee name

5. From/Drawer:
   - Look in top left corner
   - Get the full name(s)
   - May include multiple names (e.g. "John and Jane Smith")

6. From Address:
   - Look in top left corner below the name
   - Get complete address if present

7. Memo:
   - Look in bottom left corner
   - May be blank

8. Bank Name:
   - Usually prominently displayed at top

Return ONLY a valid JSON object with these exact fields (no markdown, no other text):
{
    "check_number": "string - ONLY the 3-4 digit check number from top right",
    "amount": "string - format as $X,XXX.XX",
    "date": "string - format as MM/DD/YYYY",
    "payee": "string - full payee name",
    "from": "string - name who wrote check",
    "from_address": "string - address or empty string",
    "memo": "string - memo text or empty string",
    "bank_name": "string - name of bank"
}"""

        try:
            response = await self._make_request("api/generate", data={
                "model": self.vision_model,
                "stream": False,
                "prompt": prompt,
                "images": [image_data]
            })
            
            response_text = response.get('response', '')
            logger.debug(f"Raw response: {response_text}")
            
            # Try to extract JSON from the response
            try:
                # First try direct JSON parsing
                try:
                    return json.loads(response_text)
                except json.JSONDecodeError:
                    pass
                
                # Try to find JSON-like content
                matches = re.findall(r'\{[^}]+\}', response_text.replace('\n', ' '))
                for match in matches:
                    try:
                        result = json.loads(match)
                        # Validate it has the expected fields
                        required_fields = ['check_number', 'amount', 'date', 'payee', 'from']
                        if all(field in result for field in required_fields):
                            return result
                    except json.JSONDecodeError:
                        continue
                
                # If we get here, try to parse markdown-style response
                data = {}
                for line in response_text.split('\n'):
                    line = line.strip('* ')
                    if ':' in line:
                        key, value = line.split(':', 1)
                        key = key.strip().lower().replace(' ', '_')
                        value = value.strip()
                        if key in ['check_number', 'amount', 'date', 'payee', 'from', 'from_address', 'memo', 'bank_name']:
                            data[key] = value
                
                if data and all(k in data for k in ['check_number', 'amount', 'date', 'payee', 'from']):
                    return data
                
                return {}
            except Exception as e:
                logger.error(f"Failed to parse response: {str(e)}")
                return {}
        except Exception as e:
            logger.error(f"Error analyzing image {image_path}: {str(e)}")
            raise
