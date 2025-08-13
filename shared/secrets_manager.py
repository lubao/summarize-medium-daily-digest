"""
AWS Secrets Manager utility functions for retrieving sensitive credentials.
"""
import json
import logging
from typing import Dict, Optional

import boto3
from botocore.exceptions import ClientError, NoCredentialsError

logger = logging.getLogger(__name__)


class SecretsManagerError(Exception):
    """Custom exception for Secrets Manager operations."""
    pass


def get_secret(secret_name: str, region_name: str = "us-east-1") -> Dict:
    """
    Retrieve secret value from AWS Secrets Manager.
    
    Args:
        secret_name: Name of the secret to retrieve
        region_name: AWS region where the secret is stored
        
    Returns:
        Dictionary containing the secret value
        
    Raises:
        SecretsManagerError: If secret retrieval fails
    """
    try:
        # Create a Secrets Manager client
        session = boto3.session.Session()
        client = session.client(
            service_name='secretsmanager',
            region_name=region_name
        )
        
        logger.info(f"Retrieving secret: {secret_name}")
        
        # Retrieve the secret value
        response = client.get_secret_value(SecretId=secret_name)
        
        # Parse the secret string
        secret_string = response['SecretString']
        
        try:
            # Try to parse as JSON first
            secret_data = json.loads(secret_string)
        except json.JSONDecodeError:
            # If not JSON, return as plain string in a dict
            secret_data = {"value": secret_string}
        
        logger.info(f"Successfully retrieved secret: {secret_name}")
        return secret_data
        
    except ClientError as e:
        error_code = e.response['Error']['Code']
        error_message = e.response['Error']['Message']
        
        if error_code == 'ResourceNotFoundException':
            raise SecretsManagerError(f"Secret '{secret_name}' not found: {error_message}")
        elif error_code == 'InvalidRequestException':
            raise SecretsManagerError(f"Invalid request for secret '{secret_name}': {error_message}")
        elif error_code == 'InvalidParameterException':
            raise SecretsManagerError(f"Invalid parameter for secret '{secret_name}': {error_message}")
        elif error_code == 'DecryptionFailureException':
            raise SecretsManagerError(f"Failed to decrypt secret '{secret_name}': {error_message}")
        elif error_code == 'InternalServiceErrorException':
            raise SecretsManagerError(f"Internal service error retrieving secret '{secret_name}': {error_message}")
        else:
            raise SecretsManagerError(f"Unexpected error retrieving secret '{secret_name}': {error_message}")
            
    except NoCredentialsError:
        raise SecretsManagerError("AWS credentials not found or invalid")
    except Exception as e:
        raise SecretsManagerError(f"Unexpected error retrieving secret '{secret_name}': {str(e)}")


def get_medium_cookies(region_name: str = "us-east-1") -> list:
    """
    Retrieve Medium authentication cookies from Secrets Manager.
    
    Args:
        region_name: AWS region where the secret is stored
        
    Returns:
        Medium cookies as a list of cookie objects
        
    Raises:
        SecretsManagerError: If cookie retrieval fails
    """
    try:
        secret_data = get_secret("medium-cookies", region_name)
        
        # Handle JSON array format (new format)
        if isinstance(secret_data, dict):
            cookies = secret_data.get("cookies") or secret_data.get("value")
        else:
            cookies = secret_data
            
        if not cookies:
            raise SecretsManagerError("Medium cookies not found in secret")
        
        # Parse cookies based on format
        if isinstance(cookies, str):
            try:
                # Try to parse as JSON array first (new format)
                cookies_list = json.loads(cookies)
                if isinstance(cookies_list, list):
                    logger.info("Successfully retrieved Medium cookies in JSON array format", 
                               cookie_count=len(cookies_list))
                    return cookies_list
                else:
                    # Handle legacy string format
                    logger.info("Retrieved Medium cookies in legacy string format, converting...")
                    return _convert_legacy_cookies_to_json(cookies)
            except json.JSONDecodeError:
                # Handle legacy string format
                logger.info("Retrieved Medium cookies in legacy string format, converting...")
                return _convert_legacy_cookies_to_json(cookies)
        elif isinstance(cookies, list):
            logger.info("Successfully retrieved Medium cookies in JSON array format", 
                       cookie_count=len(cookies))
            return cookies
        else:
            raise SecretsManagerError("Invalid cookie format in secret")
            
    except Exception as e:
        logger.error(f"Failed to retrieve Medium cookies: {str(e)}")
        raise SecretsManagerError(f"Failed to retrieve Medium cookies: {str(e)}")


def _convert_legacy_cookies_to_json(cookies_string: str) -> list:
    """
    Convert legacy cookie string format to JSON array format.
    
    Args:
        cookies_string: Legacy cookie string (e.g., "key1=value1; key2=value2")
        
    Returns:
        List of cookie objects in JSON format
    """
    cookies_list = []
    
    if not cookies_string:
        return cookies_list
    
    # Split by semicolon and parse each cookie
    for cookie_pair in cookies_string.split(';'):
        cookie_pair = cookie_pair.strip()
        if '=' in cookie_pair:
            key, value = cookie_pair.split('=', 1)
            cookie_obj = {
                "domain": ".medium.com",
                "hostOnly": False,
                "httpOnly": True,
                "name": key.strip(),
                "path": "/",
                "sameSite": "no_restriction",
                "secure": True,
                "session": False,
                "storeId": None,
                "value": value.strip()
            }
            cookies_list.append(cookie_obj)
    
    return cookies_list


def parse_medium_cookies(cookies_json: str) -> list:
    """
    Parse JSON-formatted Medium cookies.
    
    Args:
        cookies_json: JSON string containing cookie array
        
    Returns:
        List of cookie objects
        
    Raises:
        SecretsManagerError: If parsing fails
    """
    try:
        cookies = json.loads(cookies_json)
        if not isinstance(cookies, list):
            raise SecretsManagerError("Cookies must be a JSON array")
        return cookies
    except json.JSONDecodeError as e:
        raise SecretsManagerError(f"Invalid JSON format for cookies: {str(e)}")


def format_cookies_for_requests(cookies: list) -> dict:
    """
    Convert cookie objects to format suitable for HTTP requests.
    
    Args:
        cookies: List of cookie objects from JSON format
        
    Returns:
        Dictionary of cookie name-value pairs for requests library
    """
    cookie_dict = {}
    
    for cookie in cookies:
        if isinstance(cookie, dict) and 'name' in cookie and 'value' in cookie:
            cookie_dict[cookie['name']] = cookie['value']
    
    return cookie_dict


def get_slack_webhook_url(region_name: str = "us-east-1") -> str:
    """
    Retrieve Slack webhook URL from Secrets Manager.
    
    Args:
        region_name: AWS region where the secret is stored
        
    Returns:
        Slack webhook URL as a string
        
    Raises:
        SecretsManagerError: If webhook URL retrieval fails
    """
    try:
        secret_data = get_secret("slack-webhook-url", region_name)
        
        # Handle both JSON format and plain string format
        if isinstance(secret_data, dict):
            webhook_url = secret_data.get("webhook_url") or secret_data.get("url") or secret_data.get("value")
        else:
            webhook_url = secret_data
            
        if not webhook_url:
            raise SecretsManagerError("Slack webhook URL not found in secret")
            
        # Basic URL validation
        if not webhook_url.startswith("https://hooks.slack.com/"):
            raise SecretsManagerError("Invalid Slack webhook URL format")
            
        logger.info("Successfully retrieved Slack webhook URL")
        return webhook_url
        
    except Exception as e:
        logger.error(f"Failed to retrieve Slack webhook URL: {str(e)}")
        raise SecretsManagerError(f"Failed to retrieve Slack webhook URL: {str(e)}")


def handle_secret_errors(func):
    """
    Decorator to handle common secret retrieval errors.
    
    Args:
        func: Function to wrap with error handling
        
    Returns:
        Wrapped function with error handling
    """
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except SecretsManagerError:
            # Re-raise SecretsManagerError as-is
            raise
        except Exception as e:
            # Wrap other exceptions
            raise SecretsManagerError(f"Unexpected error in {func.__name__}: {str(e)}")
    
    return wrapper