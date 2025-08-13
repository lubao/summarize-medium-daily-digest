"""
Integration tests for the Send to Slack Lambda function.

These tests verify the function works correctly with real AWS services
and external dependencies (mocked appropriately for testing).
"""
import json
import pytest
from unittest.mock import Mock, patch, MagicMock
import requests

from lambdas.send_to_slack import lambda_handler
from shared.secrets_manager import SecretsManagerError


class TestSendToSlackIntegration:
    """Integration test cases for Send to Slack Lambda function."""
    
    @patch('lambdas.send_to_slack.requests.post')
    @patch('shared.secrets_manager.boto3.session.Session')
    def test_complete_workflow_success(self, mock_session, mock_post):
        """Test complete workflow from event to Slack message delivery."""
        # Mock AWS Secrets Manager
        mock_client = Mock()
        mock_session.return_value.client.return_value = mock_client
        mock_client.get_secret_value.return_value = {
            'SecretString': 'https://hooks.slack.com/services/T123/B456/xyz789'
        }
        
        # Mock successful Slack webhook response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response
        
        # Test event
        event = {
            "url": "https://medium.com/@author/test-article-123",
            "title": "How to Build Scalable Applications",
            "summary": "This article discusses best practices for building scalable applications using modern architecture patterns."
        }
        
        # Execute Lambda handler
        result = lambda_handler(event, None)
        
        # Verify successful processing
        assert result["statusCode"] == 200
        assert result["body"]["success"] is True
        assert result["body"]["article_title"] == "How to Build Scalable Applications"
        assert result["body"]["article_url"] == "https://medium.com/@author/test-article-123"
        
        # Verify Secrets Manager was called
        mock_client.get_secret_value.assert_called_once_with(SecretId="slack-webhook-url")
        
        # Verify Slack webhook was called with correct payload
        expected_message = "📌 *How to Build Scalable Applications*\n\n📝 This article discusses best practices for building scalable applications using modern architecture patterns.\n\n🔗 link：https://medium.com/@author/test-article-123"
        mock_post.assert_called_once_with(
            "https://hooks.slack.com/services/T123/B456/xyz789",
            json={"summary": expected_message},
            headers={'Content-Type': 'application/json'},
            timeout=30
        )
    
    @patch('lambdas.send_to_slack.requests.post')
    @patch('shared.secrets_manager.boto3.session.Session')
    def test_workflow_with_json_secret_format(self, mock_session, mock_post):
        """Test workflow with JSON-formatted secret."""
        # Mock AWS Secrets Manager with JSON format
        mock_client = Mock()
        mock_session.return_value.client.return_value = mock_client
        mock_client.get_secret_value.return_value = {
            'SecretString': json.dumps({
                "webhook_url": "https://hooks.slack.com/services/T123/B456/xyz789"
            })
        }
        
        # Mock successful Slack webhook response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response
        
        # Test event
        event = {
            "url": "https://medium.com/test-article",
            "title": "Test Article",
            "summary": "Test summary"
        }
        
        # Execute Lambda handler
        result = lambda_handler(event, None)
        
        # Verify successful processing
        assert result["statusCode"] == 200
        assert result["body"]["success"] is True
        
        # Verify webhook was called
        mock_post.assert_called_once()
    
    @patch('lambdas.send_to_slack.requests.post')
    @patch('shared.secrets_manager.boto3.session.Session')
    def test_workflow_with_retry_on_rate_limit(self, mock_session, mock_post):
        """Test workflow with retry logic on rate limiting."""
        # Mock AWS Secrets Manager
        mock_client = Mock()
        mock_session.return_value.client.return_value = mock_client
        mock_client.get_secret_value.return_value = {
            'SecretString': 'https://hooks.slack.com/services/T123/B456/xyz789'
        }
        
        # Mock rate limited response followed by success
        mock_rate_limit_response = Mock()
        mock_rate_limit_response.status_code = 429
        
        mock_success_response = Mock()
        mock_success_response.status_code = 200
        
        mock_post.side_effect = [mock_rate_limit_response, mock_success_response]
        
        # Test event
        event = {
            "url": "https://medium.com/test-article",
            "title": "Test Article",
            "summary": "Test summary"
        }
        
        # Execute Lambda handler
        result = lambda_handler(event, None)
        
        # Verify successful processing after retry
        assert result["statusCode"] == 200
        assert result["body"]["success"] is True
        
        # Verify webhook was called twice (initial + retry)
        assert mock_post.call_count == 2
    
    @patch('lambdas.send_to_slack.requests.post')
    @patch('shared.secrets_manager.boto3.session.Session')
    def test_workflow_with_server_error_retry(self, mock_session, mock_post):
        """Test workflow with retry logic on server errors."""
        # Mock AWS Secrets Manager
        mock_client = Mock()
        mock_session.return_value.client.return_value = mock_client
        mock_client.get_secret_value.return_value = {
            'SecretString': 'https://hooks.slack.com/services/T123/B456/xyz789'
        }
        
        # Mock server error response followed by success
        mock_error_response = Mock()
        mock_error_response.status_code = 500
        
        mock_success_response = Mock()
        mock_success_response.status_code = 200
        
        mock_post.side_effect = [mock_error_response, mock_success_response]
        
        # Test event
        event = {
            "url": "https://medium.com/test-article",
            "title": "Test Article",
            "summary": "Test summary"
        }
        
        # Execute Lambda handler
        result = lambda_handler(event, None)
        
        # Verify successful processing after retry
        assert result["statusCode"] == 200
        assert result["body"]["success"] is True
        
        # Verify webhook was called twice (initial + retry)
        assert mock_post.call_count == 2
    
    @patch('lambdas.send_to_slack.requests.post')
    @patch('shared.secrets_manager.boto3.session.Session')
    def test_workflow_with_connection_error_retry(self, mock_session, mock_post):
        """Test workflow with retry logic on connection errors."""
        # Mock AWS Secrets Manager
        mock_client = Mock()
        mock_session.return_value.client.return_value = mock_client
        mock_client.get_secret_value.return_value = {
            'SecretString': 'https://hooks.slack.com/services/T123/B456/xyz789'
        }
        
        # Mock connection error followed by success
        mock_success_response = Mock()
        mock_success_response.status_code = 200
        
        mock_post.side_effect = [requests.exceptions.ConnectionError(), mock_success_response]
        
        # Test event
        event = {
            "url": "https://medium.com/test-article",
            "title": "Test Article",
            "summary": "Test summary"
        }
        
        # Execute Lambda handler
        result = lambda_handler(event, None)
        
        # Verify successful processing after retry
        assert result["statusCode"] == 200
        assert result["body"]["success"] is True
        
        # Verify webhook was called twice (initial + retry)
        assert mock_post.call_count == 2
    
    @patch('shared.secrets_manager.boto3.session.Session')
    def test_workflow_with_secrets_manager_error(self, mock_session):
        """Test workflow with Secrets Manager errors."""
        # Mock AWS Secrets Manager error
        mock_client = Mock()
        mock_session.return_value.client.return_value = mock_client
        mock_client.get_secret_value.side_effect = Exception("Secret not found")
        
        # Test event
        event = {
            "url": "https://medium.com/test-article",
            "title": "Test Article",
            "summary": "Test summary"
        }
        
        # Execute Lambda handler
        result = lambda_handler(event, None)
        
        # Verify error handling
        assert result["statusCode"] == 500
        assert "Secret not found" in result["body"]["message"]
    
    @patch('lambdas.send_to_slack.requests.post')
    @patch('shared.secrets_manager.boto3.session.Session')
    def test_workflow_with_persistent_webhook_failure(self, mock_session, mock_post):
        """Test workflow when webhook fails persistently."""
        # Mock AWS Secrets Manager
        mock_client = Mock()
        mock_session.return_value.client.return_value = mock_client
        mock_client.get_secret_value.return_value = {
            'SecretString': 'https://hooks.slack.com/services/T123/B456/xyz789'
        }
        
        # Mock persistent failure (all retries fail)
        mock_error_response = Mock()
        mock_error_response.status_code = 500
        mock_post.return_value = mock_error_response
        
        # Test event
        event = {
            "url": "https://medium.com/test-article",
            "title": "Test Article",
            "summary": "Test summary"
        }
        
        # Execute Lambda handler
        result = lambda_handler(event, None)
        
        # Verify error handling
        assert result["statusCode"] == 500
        assert "Slack webhook server error" in result["body"]["message"]
        
        # Verify all retry attempts were made (1 initial + 3 retries = 4 total)
        assert mock_post.call_count == 4
    
    @patch('lambdas.send_to_slack.requests.post')
    @patch('shared.secrets_manager.boto3.session.Session')
    def test_workflow_with_article_wrapped_in_event(self, mock_session, mock_post):
        """Test workflow with article data wrapped in event structure."""
        # Mock AWS Secrets Manager
        mock_client = Mock()
        mock_session.return_value.client.return_value = mock_client
        mock_client.get_secret_value.return_value = {
            'SecretString': 'https://hooks.slack.com/services/T123/B456/xyz789'
        }
        
        # Mock successful Slack webhook response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response
        
        # Test event with wrapped article data (as might come from Step Functions)
        event = {
            "article": {
                "url": "https://medium.com/test-article",
                "title": "Wrapped Article",
                "summary": "This article data is wrapped in an 'article' key",
                "content": "Full content (should be ignored)"
            }
        }
        
        # Execute Lambda handler
        result = lambda_handler(event, None)
        
        # Verify successful processing
        assert result["statusCode"] == 200
        assert result["body"]["success"] is True
        assert result["body"]["article_title"] == "Wrapped Article"
        
        # Verify correct message was sent
        expected_message = "📌 *Wrapped Article*\n\n📝 This article data is wrapped in an 'article' key\n\n🔗 link：https://medium.com/test-article"
        mock_post.assert_called_once_with(
            "https://hooks.slack.com/services/T123/B456/xyz789",
            json={"summary": expected_message},
            headers={'Content-Type': 'application/json'},
            timeout=30
        )
    
    @patch('lambdas.send_to_slack.requests.post')
    @patch('shared.secrets_manager.boto3.session.Session')
    def test_workflow_with_special_characters_and_emojis(self, mock_session, mock_post):
        """Test workflow with special characters and emojis in article data."""
        # Mock AWS Secrets Manager
        mock_client = Mock()
        mock_session.return_value.client.return_value = mock_client
        mock_client.get_secret_value.return_value = {
            'SecretString': 'https://hooks.slack.com/services/T123/B456/xyz789'
        }
        
        # Mock successful Slack webhook response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response
        
        # Test event with special characters and emojis
        event = {
            "url": "https://medium.com/@author/special-chars-article",
            "title": "Article with 🚀 Emojis & *Special* Characters!",
            "summary": "This summary contains: @mentions, #hashtags, $symbols, and emojis 🎉✨🔥"
        }
        
        # Execute Lambda handler
        result = lambda_handler(event, None)
        
        # Verify successful processing
        assert result["statusCode"] == 200
        assert result["body"]["success"] is True
        
        # Verify message formatting preserves special characters
        expected_message = "📌 *Article with 🚀 Emojis & *Special* Characters!*\n\n📝 This summary contains: @mentions, #hashtags, $symbols, and emojis 🎉✨🔥\n\n🔗 link：https://medium.com/@author/special-chars-article"
        mock_post.assert_called_once_with(
            "https://hooks.slack.com/services/T123/B456/xyz789",
            json={"summary": expected_message},
            headers={'Content-Type': 'application/json'},
            timeout=30
        )
    
    @patch('lambdas.send_to_slack.requests.post')
    @patch('shared.secrets_manager.boto3.session.Session')
    def test_workflow_with_timeout_retry(self, mock_session, mock_post):
        """Test workflow with timeout followed by successful retry."""
        # Mock AWS Secrets Manager
        mock_client = Mock()
        mock_session.return_value.client.return_value = mock_client
        mock_client.get_secret_value.return_value = {
            'SecretString': 'https://hooks.slack.com/services/T123/B456/xyz789'
        }
        
        # Mock timeout followed by success
        mock_success_response = Mock()
        mock_success_response.status_code = 200
        
        mock_post.side_effect = [requests.exceptions.Timeout(), mock_success_response]
        
        # Test event
        event = {
            "url": "https://medium.com/test-article",
            "title": "Test Article",
            "summary": "Test summary"
        }
        
        # Execute Lambda handler
        result = lambda_handler(event, None)
        
        # Verify successful processing after retry
        assert result["statusCode"] == 200
        assert result["body"]["success"] is True
        
        # Verify webhook was called twice (initial + retry)
        assert mock_post.call_count == 2
    
    @patch('shared.secrets_manager.boto3.session.Session')
    def test_workflow_with_invalid_secret_format(self, mock_session):
        """Test workflow with invalid secret format."""
        # Mock AWS Secrets Manager with invalid secret
        mock_client = Mock()
        mock_session.return_value.client.return_value = mock_client
        mock_client.get_secret_value.return_value = {
            'SecretString': json.dumps({
                "invalid_key": "https://hooks.slack.com/services/T123/B456/xyz789"
            })
        }
        
        # Test event
        event = {
            "url": "https://medium.com/test-article",
            "title": "Test Article",
            "summary": "Test summary"
        }
        
        # Execute Lambda handler
        result = lambda_handler(event, None)
        
        # Verify error handling
        assert result["statusCode"] == 500
        assert "Slack webhook URL not found in secret" in result["body"]["message"]
    
    @patch('lambdas.send_to_slack.requests.post')
    @patch('shared.secrets_manager.boto3.session.Session')
    def test_workflow_with_client_error_no_retry(self, mock_session, mock_post):
        """Test workflow with client error that should not be retried."""
        # Mock AWS Secrets Manager
        mock_client = Mock()
        mock_session.return_value.client.return_value = mock_client
        mock_client.get_secret_value.return_value = {
            'SecretString': 'https://hooks.slack.com/services/T123/B456/xyz789'
        }
        
        # Mock client error (400 Bad Request)
        mock_error_response = Mock()
        mock_error_response.status_code = 400
        mock_error_response.text = "Bad Request - Invalid payload"
        mock_post.return_value = mock_error_response
        
        # Test event
        event = {
            "url": "https://medium.com/test-article",
            "title": "Test Article",
            "summary": "Test summary"
        }
        
        # Execute Lambda handler
        result = lambda_handler(event, None)
        
        # Verify error handling
        assert result["statusCode"] == 500
        assert "Slack webhook failed with status 400" in result["body"]["message"]
        
        # Verify webhook was called only once (no retries for client errors)
        assert mock_post.call_count == 1