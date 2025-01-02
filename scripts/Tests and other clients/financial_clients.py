from abc import ABC, abstractmethod
from typing import List, Dict, Optional
from datetime import datetime, timedelta
import plaid
import os
from dotenv import load_dotenv
import json
import asyncio
import logging
import time
from playwright.async_api import async_playwright
from tenacity import retry, stop_after_attempt, wait_exponential
from cryptography.fernet import Fernet
from .nova_client import NovaClient
from .check_utils import CheckProcessor
from src.config import (
    PLAID_CLIENT_ID, PLAID_SECRET,
    BOFA_USERNAME, BOFA_PASSWORD, BOFA_ACCOUNT_NUMBER,
    WELLS_FARGO_USERNAME, WELLS_FARGO_PASSWORD, WELLS_FARGO_ACCOUNT_NUMBER
)
import re
from bill import Bill

# Load environment variables
load_dotenv()

class FinancialClient(ABC):
    @abstractmethod
    async def get_transactions(self, start_date: datetime, end_date: datetime) -> List[Dict]:
        pass

    @abstractmethod
    async def get_check_image(self, transaction_id: str) -> Optional[bytes]:
        pass

class BankOfAmericaClient(FinancialClient):
    def __init__(self):
        self.username = BOFA_USERNAME
        self.password = BOFA_PASSWORD
        self.account_number = BOFA_ACCOUNT_NUMBER
        self.base_url = "https://www.bankofamerica.com"
        self.nova_client = NovaClient()
        self.check_processor = CheckProcessor()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    async def login(self, page):
        """Login to Bank of America"""
        try:
            # Go to login page and wait for it to load
            await page.goto(f"{self.base_url}/login/sign-in/signOnV2Screen.go", timeout=60000)
            await page.wait_for_selector('input[name="onlineId"]', timeout=10000)
            
            # Fill in credentials
            await page.fill('input[name="onlineId"]', self.username)
            await page.fill('input[name="passcode"]', self.password)
            
            # Click sign in and wait for navigation
            await page.click('button[name="enter-online-id-submit"]')
            await page.wait_for_load_state('networkidle', timeout=60000)
            
            # Check for security questions or verification
            try:
                # Look for common security elements
                security_selectors = [
                    '#tlpvt-challenge-answer',  # Security question
                    '#yes-recognize',  # Remember device
                    '#btnARContinue'   # Continue button
                ]
                
                for selector in security_selectors:
                    try:
                        element = await page.wait_for_selector(selector, timeout=5000)
                        if element:
                            logger.warning(f"Security element found: {selector} - manual intervention needed")
                            # Wait for manual intervention
                            await page.wait_for_selector(selector, state='hidden', timeout=300000)
                    except:
                        continue
            except Exception as e:
                logger.debug(f"No security intervention needed: {str(e)}")
            
            # Verify we're logged in by checking for common dashboard elements
            try:
                await page.wait_for_selector('.account-tile', timeout=10000)
                logger.info("Successfully logged into Bank of America")
                return True
            except Exception as e:
                logger.error(f"Failed to verify login success: {str(e)}")
                return False
                
        except Exception as e:
            logger.error(f"Login failed: {str(e)}")
            return False

    async def get_check_images(self, page, transaction_id) -> List[Dict]:
        """Get check images from Bank of America for a specific transaction.
        Each transaction may contain multiple checks, each with front and back images."""
        try:
            # Click into the transaction detail
            await page.click(f'[data-transaction-id="{transaction_id}"]')
            await page.wait_for_selector('.check-image-container')
            
            check_images = []
            
            # Look for multiple check containers
            check_containers = await page.query_selector_all('.check-container')
            
            for i, container in enumerate(check_containers):
                # Find and click the "View Check Image" button for this check
                view_check_button = await container.query_selector('.view-check-image')
                if view_check_button:
                    await view_check_button.click()
                    await page.wait_for_selector('.check-image')
                    
                    # Get both front and back images if available
                    front_image = await page.query_selector('.check-front-image')
                    back_image = await page.query_selector('.check-back-image')
                    
                    check_data = {
                        'check_index': i + 1,  # 1-based index for the check
                        'images': []
                    }
                    
                    # Process front image
                    if front_image:
                        front_src = await front_image.get_attribute('src')
                        front_response = await page.goto(front_src)
                        front_image_data = await front_response.body()
                        check_data['images'].append({
                            'type': 'front',
                            'data': front_image_data
                        })
                        
                        # Analyze front image with Nova
                        nova_results = self.nova_client.analyze_check_image(front_image_data)
                        if 'error' not in nova_results:
                            check_data.update({
                                'nova_analysis': nova_results,
                                'extracted_amount': nova_results.get('amount'),
                                'extracted_date': nova_results.get('date'),
                                'extracted_payee': nova_results.get('payee'),
                                'extracted_check_number': nova_results.get('check_number'),
                                'extracted_routing_number': nova_results.get('routing_number'),
                                'confidence_score': nova_results.get('confidence_score', 0)
                            })
                    
                    # Process back image
                    if back_image:
                        back_src = await back_image.get_attribute('src')
                        back_response = await page.goto(back_src)
                        check_data['images'].append({
                            'type': 'back',
                            'data': await back_response.body()
                        })
                    
                    # Get check amount if available
                    amount_elem = await container.query_selector('.check-amount')
                    if amount_elem:
                        amount_text = await amount_elem.inner_text()
                        check_data['amount'] = float(amount_text.replace('$', '').replace(',', ''))
                    
                    # Get check number if available
                    check_num_elem = await container.query_selector('.check-number')
                    if check_num_elem:
                        check_num = await check_num_elem.inner_text()
                        check_data['check_number'] = check_num
                    
                    check_images.append(check_data)
                    
                    # Close the check image viewer if there's a close button
                    close_button = await page.query_selector('.close-check-image')
                    if close_button:
                        await close_button.click()
                        await page.wait_for_selector('.check-container')
            
            return check_images if check_images else None
            
        except Exception as e:
            print(f"Error getting check images: {str(e)}")
            return None

    async def get_transactions(self, start_date: datetime, end_date: datetime) -> List[Dict]:
        """Get transactions from Bank of America"""
        transactions = []
        try:
            async with async_playwright() as p:
                # Launch visible browser for testing
                browser = await p.chromium.launch(
                    headless=False,  # Make browser visible
                    slow_mo=100  # Add slight delay to see actions
                )
                page = await browser.new_page()
                
                if await self.login(page):
                    # Navigate to accounts overview
                    await page.goto(f"{self.base_url}/myaccounts/brain/redirect.go?source=overview&target=acctDetails")
                    await page.wait_for_selector('.account-tile')
                    
                    # Add delay to see the page
                    await asyncio.sleep(2)
                    
                    # Find and click the correct account using last 4 digits
                    account_tiles = await page.query_selector_all('.account-tile')
                    for tile in account_tiles:
                        account_text = await tile.inner_text()
                        if self.account_number[-4:] in account_text:
                            await tile.click()
                            break
                    
                    # Wait for transaction list to load
                    await page.wait_for_selector('.transaction-list')
                    await asyncio.sleep(2)  # Add delay to see transactions
                    
                    # Set date range if available
                    date_filter = await page.query_selector('.date-filter')
                    if date_filter:
                        await date_filter.click()
                        await page.fill('.start-date', start_date.strftime("%m/%d/%Y"))
                        await page.fill('.end-date', end_date.strftime("%m/%d/%Y"))
                        await page.click('.apply-filter')
                        await page.wait_for_load_state('networkidle')
                    
                    # Extract transactions
                    rows = await page.query_selector_all('.transaction-row')
                    for row in rows:
                        date_text = await row.query_selector('.date')
                        desc_text = await row.query_selector('.description')
                        amount_text = await row.query_selector('.amount')
                        
                        if date_text and desc_text and amount_text:
                            date = await date_text.inner_text()
                            description = await desc_text.inner_text()
                            amount_str = (await amount_text.inner_text()).replace('$', '').replace(',', '')
                            transaction_id = await row.get_attribute('data-transaction-id')
                            
                            transaction = {
                                'date': datetime.strptime(date, "%m/%d/%Y").strftime("%Y-%m-%d"),
                                'description': description.strip(),
                                'amount': float(amount_str),
                                'type': 'check' if 'Check #' in description else 'other',
                                'source': 'bofa',
                                'account_last4': self.account_number[-4:],
                                'transaction_id': transaction_id
                            }
                            
                            # If it's a check, extract the check number
                            if transaction['type'] == 'check':
                                check_match = re.search(r'Check #(\d+)', description)
                                if check_match:
                                    transaction['check_number'] = check_match.group(1)
                            
                            # If it's a deposit, try to get check images
                            if amount_str.startswith('+') or float(amount_str) > 0:
                                check_images = await self.get_check_images(page, transaction_id)
                                if check_images:
                                    transaction['checks'] = check_images
                                    transaction['num_checks'] = len(check_images)
                                    transaction['has_check_images'] = True
                                    
                                    # Save check images and update paths
                                    saved_paths = self.check_processor.save_check_images(transaction, 'bofa')
                                    transaction['check_image_paths'] = saved_paths
                                    
                                    # Validate check amounts
                                    amount_validation = self.check_processor.validate_check_amounts(transaction)
                                    transaction['amount_validation'] = amount_validation
                                    
                                    # Validate confidence scores
                                    confidence_validation = self.check_processor.validate_confidence_scores(transaction)
                                    transaction['confidence_validation'] = confidence_validation
                                    
                                    # Add validation summary
                                    transaction['validation_status'] = {
                                        'valid': amount_validation['valid'] and confidence_validation['valid'],
                                        'issues': []
                                    }
                                    
                                    if not amount_validation['valid']:
                                        transaction['validation_status']['issues'].append({
                                            'type': 'amount_mismatch',
                                            'details': amount_validation['reason']
                                        })
                                    
                                    if not confidence_validation['valid']:
                                        transaction['validation_status']['issues'].append({
                                            'type': 'low_confidence',
                                            'details': confidence_validation['reason'],
                                            'checks': confidence_validation.get('low_confidence_checks', [])
                                        })
                                else:
                                    transaction['has_check_images'] = False
                                    transaction['num_checks'] = 0
                            
                            transactions.append(transaction)
                            
                            # Go back to transaction list if we navigated away
                            if page.url != f"{self.base_url}/myaccounts/brain/redirect.go?source=overview&target=acctDetails":
                                await page.go_back()
                                await page.wait_for_selector('.transaction-list')
                
                await browser.close()
        except Exception as e:
            print(f"Error getting transactions: {str(e)}")
        
        return transactions

    async def get_check_image(self, transaction_id: str) -> Optional[bytes]:
        """Get check image from Bank of America"""
        try:
            async with async_playwright() as p:
                # Launch visible browser for testing
                browser = await p.chromium.launch(
                    headless=False,  # Make browser visible
                    slow_mo=100  # Add slight delay to see actions
                )
                page = await browser.new_page()
                
                if await self.login(page):
                    # Navigate to check image
                    await page.goto(f"{self.base_url}/checkimage/{transaction_id}")
                    await page.wait_for_selector("#check-image")

                    # Download image
                    image_element = await page.query_selector("#check-image")
                    if image_element:
                        return await image_element.screenshot()
                
                await browser.close()
        except Exception as e:
            print(f"Error getting check image: {str(e)}")
        
        return None

class BillDotComClient(FinancialClient):
    def __init__(self):
        self.api_key = os.getenv('BILLDOTCOM_API_KEY')
        if not self.api_key:
            raise ValueError("Missing required Bill.com API key in environment variables")
        self.client = Bill(api_key=self.api_key)
    
    async def get_transactions(self, start_date: datetime, end_date: datetime) -> List[Dict]:
        """Get transactions from Bill.com"""
        try:
            # Convert dates to required format
            start_str = start_date.strftime("%Y-%m-%d")
            end_str = end_date.strftime("%Y-%m-%d")
            
            # Get payments from Bill.com
            payments = self.client.get_payments(
                start_date=start_str,
                end_date=end_str,
                status="paid"
            )
            
            transactions = []
            for payment in payments:
                transactions.append({
                    'id': payment.id,
                    'date': payment.payment_date,
                    'amount': float(payment.amount),
                    'description': payment.description,
                    'type': payment.payment_type,
                    'status': payment.status
                })
            
            return transactions
        except Exception as e:
            print(f"Error getting Bill.com transactions: {str(e)}")
            return []
    
    async def get_check_image(self, transaction_id: str) -> Optional[bytes]:
        """Get check image from Bill.com"""
        try:
            payment = self.client.get_payment(transaction_id)
            if payment and payment.check_image_url:
                response = self.client.session.get(payment.check_image_url)
                if response.status_code == 200:
                    return response.content
            return None
        except Exception as e:
            print(f"Error getting Bill.com check image: {str(e)}")
            return None

class WellsFargoClient(FinancialClient):
    def __init__(self):
        self.username = WELLS_FARGO_USERNAME
        self.password = WELLS_FARGO_PASSWORD
        self.account_number = WELLS_FARGO_ACCOUNT_NUMBER
        self.base_url = "https://connect.secure.wellsfargo.com"
        self.nova_client = NovaClient()
        self.check_processor = CheckProcessor()
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    async def login(self, page):
        """Login to Wells Fargo"""
        try:
            # Go to login page and wait for it to load
            await page.goto(f"{self.base_url}/auth/login", timeout=60000)
            await page.wait_for_selector('#j_username', timeout=10000)
            
            # Fill in credentials
            await page.fill('#j_username', self.username)
            await page.fill('#j_password', self.password)
            
            # Click sign in and wait for navigation
            await page.click('input[name="btnSignon"]')
            await page.wait_for_load_state('networkidle', timeout=60000)
            
            # Check for security verification
            try:
                # Look for common security elements
                security_selectors = [
                    '#securityCode',          # 2FA code input
                    '#sendCode',              # Send code button
                    '#registrationOption',    # Device registration
                    '#btnSubmit'              # Submit button
                ]
                
                for selector in security_selectors:
                    try:
                        element = await page.wait_for_selector(selector, timeout=5000)
                        if element:
                            logger.warning(f"Security element found: {selector} - manual intervention needed")
                            # Wait for manual intervention
                            await page.wait_for_selector(selector, state='hidden', timeout=300000)
                    except:
                        continue
            except Exception as e:
                logger.debug(f"No security intervention needed: {str(e)}")
            
            # Verify we're logged in by checking for common dashboard elements
            try:
                await page.wait_for_selector('.account-tile', timeout=10000)
                logger.info("Successfully logged into Wells Fargo")
                return True
            except Exception as e:
                logger.error(f"Failed to verify login success: {str(e)}")
                return False
                
        except Exception as e:
            logger.error(f"Login failed: {str(e)}")
            return False

    async def get_transactions(self, start_date: datetime, end_date: datetime) -> List[Dict]:
        """Get transactions from Wells Fargo"""
        transactions = []
        try:
            async with async_playwright() as p:
                # Launch visible browser for testing
                browser = await p.chromium.launch(
                    headless=False,  # Make browser visible
                    slow_mo=100  # Add slight delay to see actions
                )
                page = await browser.new_page()
                
                if await self.login(page):
                    # Navigate to account summary
                    await page.goto(f"{self.base_url}/accounts/inquiry/summary")
                    await page.wait_for_selector('.account-tile')
                    
                    # Add delay to see the page
                    await asyncio.sleep(2)
                    
                    # Find and click the correct account using last 4 digits
                    account_tiles = await page.query_selector_all('.account-tile')
                    for tile in account_tiles:
                        account_text = await tile.inner_text()
                        if self.account_number[-4:] in account_text:
                            await tile.click()
                            break
                    
                    # Wait for transaction list
                    await page.wait_for_selector('.transaction-list')
                    await asyncio.sleep(2)  # Add delay to see transactions
                    
                    # Set date range
                    await page.click('.date-range-selector')
                    await page.fill('#fromDate', start_date.strftime("%m/%d/%Y"))
                    await page.fill('#toDate', end_date.strftime("%m/%d/%Y"))
                    await page.click('.apply-dates')
                    await page.wait_for_load_state('networkidle')
                    
                    # Extract transactions
                    rows = await page.query_selector_all('.transaction-row')
                    for row in rows:
                        date_text = await row.query_selector('.date')
                        desc_text = await row.query_selector('.description')
                        amount_text = await row.query_selector('.amount')
                        
                        if date_text and desc_text and amount_text:
                            date = await date_text.inner_text()
                            description = await desc_text.inner_text()
                            amount_str = (await amount_text.inner_text()).replace('$', '').replace(',', '')
                            
                            transaction = {
                                'date': datetime.strptime(date, "%m/%d/%Y").strftime("%Y-%m-%d"),
                                'description': description.strip(),
                                'amount': float(amount_str),
                                'type': 'check' if 'Check #' in description else 'other',
                                'source': 'wellsfargo',
                                'account_last4': self.account_number[-4:]
                            }
                            
                            # If it's a check, extract the check number
                            if transaction['type'] == 'check':
                                check_match = re.search(r'Check #(\d+)', description)
                                if check_match:
                                    transaction['check_number'] = check_match.group(1)
                            
                            transactions.append(transaction)
                
                await browser.close()
        except Exception as e:
            print(f"Error getting transactions: {str(e)}")
        
        return transactions

    async def get_check_image(self, transaction_id: str) -> Optional[bytes]:
        """Get check image from Wells Fargo"""
        try:
            async with async_playwright() as p:
                # Launch visible browser for testing
                browser = await p.chromium.launch(
                    headless=False,  # Make browser visible
                    slow_mo=100  # Add slight delay to see actions
                )
                page = await browser.new_page()
                
                if await self.login(page):
                    # Navigate to check image
                    await page.goto(f"{self.base_url}/accounts/images/check/{transaction_id}")
                    await page.wait_for_selector("#check-front")

                    # Download image
                    image_element = await page.query_selector("#check-front")
                    if image_element:
                        return await image_element.screenshot()
                
                await browser.close()
        except Exception as e:
            print(f"Error getting check image: {str(e)}")
        
        return None
