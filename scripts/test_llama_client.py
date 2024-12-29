import asyncio
import sys
from pathlib import Path
from pdf2image import convert_from_path

# Add project root to path
project_root = str(Path(__file__).parent.parent)
sys.path.append(project_root)

from src.llama_client import LlamaClient

async def test_text():
    client = LlamaClient()
    response = await client.process_text("What is 2+2?")
    print("\nText Response:", response)

async def test_vision():
    client = LlamaClient()
    # Assuming you have a check image in your payment_matching folder
    test_pdf = Path("C:/Users/aaron/Downloads/payment_matching_20241228/44.pdf")
    if not test_pdf.exists():
        print(f"\nTest PDF not found at: {test_pdf}")
        return
        
    print(f"\nTesting vision with PDF: {test_pdf}")
    
    # Convert PDF to PNG
    poppler_path = r"C:\poppler\poppler-24.08.0\Library\bin"
    images = convert_from_path(test_pdf, poppler_path=poppler_path)
    if not images:
        print("No images found in PDF")
        return
        
    # Save first page as PNG
    test_image = test_pdf.with_suffix('.png')
    images[0].save(test_image)
    
    try:
        print(f"Converting to image: {test_image}")
        response = await client.extract_check_info(test_image)
        print("\nVision Response:", response)
    finally:
        # Clean up temporary PNG
        if test_image.exists():
            test_image.unlink()

async def main():
    await test_text()
    await test_vision()

if __name__ == "__main__":
    asyncio.run(main())
