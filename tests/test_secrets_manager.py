"""
Unit tests for secrets manager utilities.
"""
import json
import pytest
from unittest.mock import Mock, patch, MagicMock
from botocore.exceptions import ClientError, NoCredentialsError

from shared.secrets_manager import (
    get_secret,
    get_medium_cookies,
    get_slack_webhook_url,
    parse_medium_cookies,
    format_cookies_for_requests,
    handle_secret_errors,
    SecretsManagerError
)


class TestGetSecret:
    """Test cases for the get_secret function."""
    
    @patch('shared.secrets_manager.boto3.session.Session')
    def test_get_secret_json_format(self, mock_session):
        """Test retrieving secret in JSON format."""
        # Mock the boto3 client
        mock_client = Mock()
        mock_session.return_value.client.return_value = mock_client
        
        # Mock the response
        secret_data = {"key1": "value1", "key2": "value2"}
        mock_client.get_secret_value.return_value = {
            'SecretString': json.dumps(secret_data)
        }
        
        result = get_secret("test-secret")
        
        assert result == secret_data
        mock_client.get_secret_value.assert_called_once_with(SecretId="test-secret")
    
    @patch('shared.secrets_manager.boto3.session.Session')
    def test_get_secret_plain_string(self, mock_session):
        """Test retrieving secret as plain string."""
        # Mock the boto3 client
        mock_client = Mock()
        mock_session.return_value.client.return_value = mock_client
        
        # Mock the response
        secret_value = "plain-secret-value"
        mock_client.get_secret_value.return_value = {
            'SecretString': secret_value
        }
        
        result = get_secret("test-secret")
        
        assert result == {"value": secret_value}
    
    @patch('shared.secrets_manager.boto3.session.Session')
    def test_get_secret_resource_not_found(self, mock_session):
        """Test handling of ResourceNotFoundException."""
        # Mock the boto3 client
        mock_client = Mock()
        mock_session.return_value.client.return_value = mock_client
        
        # Mock the exception
        error_response = {
            'Error': {
                'Code': 'ResourceNotFoundException',
                'Message': 'Secret not found'
            }
        }
        mock_client.get_secret_value.side_effect = ClientError(error_response, 'GetSecretValue')
        
        with pytest.raises(SecretsManagerError) as exc_info:
            get_secret("nonexistent-secret")
        
        assert "Secret 'nonexistent-secret' not found" in str(exc_info.value)
    
    @patch('shared.secrets_manager.boto3.session.Session')
    def test_get_secret_decryption_failure(self, mock_session):
        """Test handling of DecryptionFailureException."""
        # Mock the boto3 client
        mock_client = Mock()
        mock_session.return_value.client.return_value = mock_client
        
        # Mock the exception
        error_response = {
            'Error': {
                'Code': 'DecryptionFailureException',
                'Message': 'Failed to decrypt'
            }
        }
        mock_client.get_secret_value.side_effect = ClientError(error_response, 'GetSecretValue')
        
        with pytest.raises(SecretsManagerError) as exc_info:
            get_secret("test-secret")
        
        assert "Failed to decrypt secret 'test-secret'" in str(exc_info.value)
    
    @patch('shared.secrets_manager.boto3.session.Session')
    def test_get_secret_no_credentials(self, mock_session):
        """Test handling of NoCredentialsError."""
        # Mock the boto3 client
        mock_client = Mock()
        mock_session.return_value.client.return_value = mock_client
        
        # Mock the exception
        mock_client.get_secret_value.side_effect = NoCredentialsError()
        
        with pytest.raises(SecretsManagerError) as exc_info:
            get_secret("test-secret")
        
        assert "AWS credentials not found or invalid" in str(exc_info.value)


class TestGetMediumCookies:
    """Test cases for the get_medium_cookies function."""
    
    @patch('shared.secrets_manager.get_secret')
    def test_get_medium_cookies_json_array_format(self, mock_get_secret):
        """Test retrieving Medium cookies from JSON array format."""
        cookies_json = json.dumps([
            {
                "domain": ".medium.com",
                "name": "uid",
                "value": "aa1a02b88c89",
                "path": "/",
                "secure": True,
                "httpOnly": True
            },
            {
                "domain": ".medium.com", 
                "name": "sid",
                "value": "1:test123",
                "path": "/",
                "secure": True,
                "httpOnly": True
            }
        ])
        mock_get_secret.return_value = {"cookies": cookies_json}
        
        result = get_medium_cookies()
        
        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0]["name"] == "uid"
        assert result[0]["value"] == "aa1a02b88c89"
        assert result[1]["name"] == "sid"
        assert result[1]["value"] == "1:test123"
        mock_get_secret.assert_called_once_with("medium-cookies", "us-east-1")
    
    @patch('shared.secrets_manager.get_secret')
    def test_get_medium_cookies_legacy_string_format(self, mock_get_secret):
        """Test retrieving Medium cookies from legacy string format."""
        cookies_value = "nonce=test; uid=123; sid=abc"
        mock_get_secret.return_value = {"cookies": cookies_value}
        
        result = get_medium_cookies()
        
        assert isinstance(result, list)
        assert len(result) == 3
        assert result[0]["name"] == "nonce"
        assert result[0]["value"] == "test"
        assert result[0]["domain"] == ".medium.com"
    
    @patch('shared.secrets_manager.get_secret')
    def test_get_medium_cookies_direct_json_array(self, mock_get_secret):
        """Test retrieving Medium cookies as direct JSON array."""
        cookies_list = [
            {"name": "test", "value": "123", "domain": ".medium.com"}
        ]
        mock_get_secret.return_value = cookies_list
        
        result = get_medium_cookies()
        
        assert result == cookies_list
    
    @patch('shared.secrets_manager.get_secret')
    def test_get_medium_cookies_empty(self, mock_get_secret):
        """Test handling of empty Medium cookies."""
        mock_get_secret.return_value = {"cookies": ""}
        
        with pytest.raises(SecretsManagerError) as exc_info:
            get_medium_cookies()
        
        assert "Medium cookies not found in secret" in str(exc_info.value)
    
    @patch('shared.secrets_manager.get_secret')
    def test_get_medium_cookies_secret_error(self, mock_get_secret):
        """Test handling of secret retrieval error."""
        mock_get_secret.side_effect = SecretsManagerError("Secret not found")
        
        with pytest.raises(SecretsManagerError) as exc_info:
            get_medium_cookies()
        
        assert "Failed to retrieve Medium cookies" in str(exc_info.value)


class TestParseMediumCookies:
    """Test cases for the parse_medium_cookies function."""
    
    def test_parse_medium_cookies_valid_json(self):
        """Test parsing valid JSON cookie array."""
        from shared.secrets_manager import parse_medium_cookies
        
        cookies_json = json.dumps([
            {"name": "test", "value": "123"},
            {"name": "uid", "value": "abc"}
        ])
        
        result = parse_medium_cookies(cookies_json)
        
        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0]["name"] == "test"
        assert result[1]["name"] == "uid"
    
    def test_parse_medium_cookies_invalid_json(self):
        """Test parsing invalid JSON."""
        from shared.secrets_manager import parse_medium_cookies
        
        with pytest.raises(SecretsManagerError) as exc_info:
            parse_medium_cookies("invalid json")
        
        assert "Invalid JSON format for cookies" in str(exc_info.value)
    
    def test_parse_medium_cookies_not_array(self):
        """Test parsing JSON that is not an array."""
        from shared.secrets_manager import parse_medium_cookies
        
        cookies_json = json.dumps({"not": "array"})
        
        with pytest.raises(SecretsManagerError) as exc_info:
            parse_medium_cookies(cookies_json)
        
        assert "Cookies must be a JSON array" in str(exc_info.value)


class TestFormatCookiesForRequests:
    """Test cases for the format_cookies_for_requests function."""
    
    def test_format_cookies_for_requests_valid(self):
        """Test formatting valid cookie objects for HTTP requests."""
        from shared.secrets_manager import format_cookies_for_requests
        
        cookies = [
            {
                "name": "uid",
                "value": "aa1a02b88c89",
                "domain": ".medium.com",
                "secure": True
            },
            {
                "name": "sid", 
                "value": "1:test123",
                "domain": ".medium.com",
                "secure": True
            }
        ]
        
        result = format_cookies_for_requests(cookies)
        
        assert isinstance(result, dict)
        assert result["uid"] == "aa1a02b88c89"
        assert result["sid"] == "1:test123"
    
    def test_format_cookies_for_requests_missing_fields(self):
        """Test formatting cookie objects with missing fields."""
        from shared.secrets_manager import format_cookies_for_requests
        
        cookies = [
            {"name": "uid", "value": "123"},  # Valid
            {"name": "incomplete"},           # Missing value
            {"value": "orphan"},             # Missing name
            {"other": "field"}               # Missing both
        ]
        
        result = format_cookies_for_requests(cookies)
        
        assert len(result) == 1
        assert result["uid"] == "123"
    
    def test_format_cookies_for_requests_empty_list(self):
        """Test formatting empty cookie list."""
        from shared.secrets_manager import format_cookies_for_requests
        
        result = format_cookies_for_requests([])
        
        assert result == {}


class TestGetSlackWebhookUrl:
    """Test cases for the get_slack_webhook_url function."""
    
    @patch('shared.secrets_manager.get_secret')
    def test_get_slack_webhook_url_json_format(self, mock_get_secret):
        """Test retrieving Slack webhook URL from JSON format."""
        webhook_url = "https://hooks.slack.com/triggers/test/webhook"
        mock_get_secret.return_value = {"webhook_url": webhook_url}
        
        result = get_slack_webhook_url()
        
        assert result == webhook_url
        mock_get_secret.assert_called_once_with("slack-webhook-url", "us-east-1")
    
    @patch('shared.secrets_manager.get_secret')
    def test_get_slack_webhook_url_alternative_keys(self, mock_get_secret):
        """Test retrieving Slack webhook URL with alternative JSON keys."""
        webhook_url = "https://hooks.slack.com/triggers/test/webhook"
        
        # Test with 'url' key
        mock_get_secret.return_value = {"url": webhook_url}
        result = get_slack_webhook_url()
        assert result == webhook_url
        
        # Test with 'value' key
        mock_get_secret.return_value = {"value": webhook_url}
        result = get_slack_webhook_url()
        assert result == webhook_url
    
    @patch('shared.secrets_manager.get_secret')
    def test_get_slack_webhook_url_plain_string(self, mock_get_secret):
        """Test retrieving Slack webhook URL as plain string."""
        webhook_url = "https://hooks.slack.com/triggers/test/webhook"
        mock_get_secret.return_value = webhook_url
        
        result = get_slack_webhook_url()
        
        assert result == webhook_url
    
    @patch('shared.secrets_manager.get_secret')
    def test_get_slack_webhook_url_invalid_format(self, mock_get_secret):
        """Test handling of invalid Slack webhook URL format."""
        invalid_url = "https://example.com/webhook"
        mock_get_secret.return_value = {"webhook_url": invalid_url}
        
        with pytest.raises(SecretsManagerError) as exc_info:
            get_slack_webhook_url()
        
        assert "Invalid Slack webhook URL format" in str(exc_info.value)
    
    @patch('shared.secrets_manager.get_secret')
    def test_get_slack_webhook_url_empty(self, mock_get_secret):
        """Test handling of empty Slack webhook URL."""
        mock_get_secret.return_value = {"webhook_url": ""}
        
        with pytest.raises(SecretsManagerError) as exc_info:
            get_slack_webhook_url()
        
        assert "Slack webhook URL not found in secret" in str(exc_info.value)


class TestHandleSecretErrors:
    """Test cases for the handle_secret_errors decorator."""
    
    def test_handle_secret_errors_success(self):
        """Test decorator with successful function execution."""
        @handle_secret_errors
        def test_function():
            return "success"
        
        result = test_function()
        assert result == "success"
    
    def test_handle_secret_errors_secrets_manager_error(self):
        """Test decorator with SecretsManagerError."""
        @handle_secret_errors
        def test_function():
            raise SecretsManagerError("Test error")
        
        with pytest.raises(SecretsManagerError) as exc_info:
            test_function()
        
        assert "Test error" in str(exc_info.value)
    
    def test_handle_secret_errors_other_exception(self):
        """Test decorator with other exceptions."""
        @handle_secret_errors
        def test_function():
            raise ValueError("Test error")
        
        with pytest.raises(SecretsManagerError) as exc_info:
            test_function()
        
        assert "Unexpected error in test_function" in str(exc_info.value)