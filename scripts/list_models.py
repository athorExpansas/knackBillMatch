"""List available Ollama models."""
import asyncio
import aiohttp
import json
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

async def list_models():
    """List available models from Ollama."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get("http://192.168.1.215:11434/api/tags") as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"API request failed ({response.status}): {error_text}")
                
                data = await response.json()
                logger.info("Available models:")
                for model in data.get('models', []):
                    logger.info(f"- {model.get('name')}")
    except Exception as e:
        logger.error(f"Error listing models: {str(e)}")

if __name__ == "__main__":
    asyncio.run(list_models())
