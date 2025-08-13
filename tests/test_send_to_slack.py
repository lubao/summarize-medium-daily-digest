"""
Unit tests for the Send to Slack Lambda function.
"""
import json
import pytest
from unittest.mock import Mock, patch, MagicMock
import requests

from lambdas.send_to_slack import (
    lambda_handler,
    format_slack_message,
    send_webhook_request
)
from shared.error_handling import NetworkError, ValidationError
from shared.secrets_manager import SecretsManagerError


class TestFormatSlackMessage:
    """Test cases for format_slack_message function."""
    
    def test_format_slack_message_success(self):
        """Test successful message formatting."""
        title = "Test Article Title"
        summary = "This is a test summary of the article."
        url = "https://medium.com/test-article"
        
        result = format_slack_message(title, summary, url)
        
        expected = "📌 *Test Article Title*\n\n📝 This is a test summary of the article.\n\n🔗 link：https://medium.com/test-article"
        assert result == expected
    
    def test_format_slack_message_with_special_characters(self):
        """Test message formatting with special characters."""
        title = "Article with *bold* and _italic_ text"
        summary = "Summary with special chars: @#$%^&*()"
        url = "https://medium.com/special-chars-article"
        
        result = format_slack_message(title, summary, url)
        
        expected = "📌 *Article with *bold* and _italic_ text*\n\n📝 Summary with special chars: @#$%^&*()\n\n🔗 link：https://medium.com/special-chars-article"
        assert result == expected
    
    def test_format_slack_message_strips_whitespace(self):
        """Test that message formatting strips whitespace."""
        title = "  Test Title  "
        summary = "  Test Summary  "
        url = "  https://medium.com/test  "
        
        result = format_slack_message(title, summary, url)
        
        expected = "📌 *Test Title*\n\n📝 Test Summary\n\n🔗 link：https://medium.com/test"
        assert result == expected
    
    def test_format_slack_message_empty_title(self):
        """Test error handling for empty title."""
        with pytest.raises(ValidationError, match="Article title is required"):
            format_slack_message("", "Summary", "https://medium.com/test")
    
    def test_format_slack_message_whitespace_only_title(self):
        """Test error handling for whitespace-only title."""
        with pytest.raises(ValidationError, match="Article title is required"):
            format_slack_message("   ", "Summary", "https://medium.com/test")
    
    def test_format_slack_message_empty_summary(self):
        """Test error handling for empty summary."""
        with pytest.raises(ValidationError, match="Article summary is required"):
            format_slack_message("Title", "", "https://medium.com/test")
    
    def test_format_slack_message_whitespace_only_summary(self):
        """Test error handling for whitespace-only summary."""
        with pytest.raises(ValidationError, match="Article summary is required"):
            format_slack_message("Title", "   ", "https://medium.com/test")
    
    def test_format_slack_message_empty_url(self):
        """Test error handling for empty URL."""
        with pytest.raises(ValidationError, match="Article URL is required"):
            format_slack_message("Title", "Summary", "")
    
    def test_format_slack_message_whitespace_only_url(self):
        """Test error handling for whitespace-only URL."""
        with pytest.raises(ValidationError, match="Article URL is required"):
            format_slack_message("Title", "Summary", "   ")
    
    def test_format_slack_message_none_values(self):
        """Test error handling for None values."""
        with pytest.raises(ValidationError, match="Article title is required"):
            format_slack_message(None, "Summary", "https://medium.com/test")
        
        with pytest.raises(ValidationError, match="Article summary is required"):
            format_slack_message("Title", None, "https://medium.com/test")
        
        with pytest.raises(ValidationError, match="Article URL is required"):
            format_slack_message("Title", "Summary", None)


class TestSendWebhookRequest:
    """Test cases for send_webhook_request function."""
    
    @patch('lambdas.send_to_slack.requests.post')
    def test_send_webhook_request_success(self, mock_post):
        """Test successful webhook request."""
        # Mock successful response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response
        
        webhook_url = "https://hooks.slack.com/services/test/webhook"
        payload = {"summary": "Test message"}
        
        result = send_webhook_request(webhook_url, payload)
        
        assert result == {"success": True, "status_code": 200}
        mock_post.assert_called_once_with(
            webhook_url,
            json=payload,
            headers={'Content-Type': 'application/json'},
            timeout=30
        )
    
    def test_send_webhook_request_invalid_url(self):
        """Test error handling for invalid webhook URL."""
        invalid_url = "https://invalid-url.com/webhook"
        payload = {"summary": "Test message"}
        
        with pytest.raises(ValidationError, match="Invalid Slack webhook URL"):
            send_webhook_request(invalid_url, payload)
    
    @patch('lambdas.send_to_slack.requests.post')
    def test_send_webhook_request_rate_limited(self, mock_post):
        """Test handling of rate limiting (429 status)."""
        mock_response = Mock()
        mock_response.status_code = 429
        mock_post.return_value = mock_response
        
        webhook_url = "https://hooks.slack.com/services/test/webhook"
        payload = {"summary": "Test message"}
        
        with pytest.raises(NetworkError, match="Slack webhook rate limited"):
            send_webhook_request(webhook_url, payload)
    
    @patch('lambdas.send_to_slack.requests.post')
    def test_send_webhook_request_server_error(self, mock_post):
        """Test handling of server errors (5xx status)."""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_post.return_value = mock_response
        
        webhook_url = "https://hooks.slack.com/services/test/webhook"
        payload = {"summary": "Test message"}
        
        with pytest.raises(NetworkError, match="Slack webhook server error"):
            send_webhook_request(webhook_url, payload)
    
    @patch('lambdas.send_to_slack.requests.post')
    def test_send_webhook_request_client_error(self, mock_post):
        """Test handling of client errors (4xx status except 429)."""
        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.text = "Bad Request"
        mock_post.return_value = mock_response
        
        webhook_url = "https://hooks.slack.com/services/test/webhook"
        payload = {"summary": "Test message"}
        
        with pytest.raises(ValidationError, match="Slack webhook failed with status 400"):
            send_webhook_request(webhook_url, payload)
    
    @patch('lambdas.send_to_slack.requests.post')
    def test_send_webhook_request_timeout(self, mock_post):
        """Test handling of request timeout."""
        mock_post.side_effect = requests.exceptions.Timeout()
        
        webhook_url = "https://hooks.slack.com/services/test/webhook"
        payload = {"summary": "Test message"}
        
        with pytest.raises(NetworkError, match="Slack webhook request timed out"):
            send_webhook_request(webhook_url, payload)
    
    @patch('lambdas.send_to_slack.requests.post')
    def test_send_webhook_request_connection_error(self, mock_post):
        """Test handling of connection error."""
        mock_post.side_effect = requests.exceptions.ConnectionError()
        
        webhook_url = "https://hooks.slack.com/services/test/webhook"
        payload = {"summary": "Test message"}
        
        with pytest.raises(NetworkError, match="Failed to connect to Slack webhook"):
            send_webhook_request(webhook_url, payload)
    
    @patch('lambdas.send_to_slack.requests.post')
    def test_send_webhook_request_general_request_exception(self, mock_post):
        """Test handling of general request exceptions."""
        mock_post.side_effect = requests.exceptions.RequestException("General error")
        
        webhook_url = "https://hooks.slack.com/services/test/webhook"
        payload = {"summary": "Test message"}
        
        with pytest.raises(NetworkError, match="Slack webhook request failed"):
            send_webhook_request(webhook_url, payload)


class TestLambdaHandler:
    """Test cases for lambda_handler function."""
    
    @patch('lambdas.send_to_slack.send_webhook_request')
    @patch('lambdas.send_to_slack.get_slack_webhook_url')
    def test_lambda_handler_success_direct_article_data(self, mock_get_webhook, mock_send_webhook):
        """Test successful processing with direct article data."""
        # Mock dependencies
        mock_get_webhook.return_value = "https://hooks.slack.com/services/test/webhook"
        mock_send_webhook.return_value = {"success": True, "status_code": 200}
        
        # Test event with direct article data
        event = {
            "url": "https://medium.com/test-article",
            "title": "Test Article",
            "summary": "This is a test summary."
        }
        
        result = lambda_handler(event, None)
        
        assert result["statusCode"] == 200
        assert result["body"]["success"] is True
        assert result["body"]["article_title"] == "Test Article"
        assert result["body"]["article_url"] == "https://medium.com/test-article"
        
        # Verify webhook was called with correct payload
        expected_message = "📌 *Test Article*\n\n📝 This is a test summary.\n\n🔗 link：https://medium.com/test-article"
        mock_send_webhook.assert_called_once_with(
            "https://hooks.slack.com/services/test/webhook",
            {"summary": expected_message}
        )
    
    @patch('lambdas.send_to_slack.send_webhook_request')
    @patch('lambdas.send_to_slack.get_slack_webhook_url')
    def test_lambda_handler_success_wrapped_article_data(self, mock_get_webhook, mock_send_webhook):
        """Test successful processing with article data wrapped in 'article' key."""
        # Mock dependencies
        mock_get_webhook.return_value = "https://hooks.slack.com/services/test/webhook"
        mock_send_webhook.return_value = {"success": True, "status_code": 200}
        
        # Test event with wrapped article data
        event = {
            "article": {
                "url": "https://medium.com/test-article",
                "title": "Test Article",
                "summary": "This is a test summary."
            }
        }
        
        result = lambda_handler(event, None)
        
        assert result["statusCode"] == 200
        assert result["body"]["success"] is True
    
    def test_lambda_handler_invalid_event_format(self):
        """Test error handling for invalid event format."""
        event = {"invalid": "data"}
        
        result = lambda_handler(event, None)
        
        assert result["statusCode"] == 500
        assert "Article title is required" in result["body"]["message"]
    
    def test_lambda_handler_missing_title(self):
        """Test error handling for missing article title."""
        event = {
            "url": "https://medium.com/test-article",
            "summary": "This is a test summary."
        }
        
        result = lambda_handler(event, None)
        
        assert result["statusCode"] == 500
        assert "Article title is required" in result["body"]["message"]
    
    def test_lambda_handler_missing_summary(self):
        """Test error handling for missing article summary."""
        event = {
            "url": "https://medium.com/test-article",
            "title": "Test Article"
        }
        
        result = lambda_handler(event, None)
        
        assert result["statusCode"] == 500
        assert "Article summary is required" in result["body"]["message"]
    
    def test_lambda_handler_missing_url(self):
        """Test error handling for missing article URL."""
        event = {
            "title": "Test Article",
            "summary": "This is a test summary."
        }
        
        result = lambda_handler(event, None)
        
        assert result["statusCode"] == 500
        assert "Article URL is required" in result["body"]["message"]
    
    @patch('lambdas.send_to_slack.get_slack_webhook_url')
    @patch('lambdas.send_to_slack.send_admin_notification')
    def test_lambda_handler_secrets_manager_error(self, mock_send_notification, mock_get_webhook):
        """Test error handling for Secrets Manager failures."""
        # Mock Secrets Manager error
        mock_get_webhook.side_effect = SecretsManagerError("Secret not found")
        
        event = {
            "url": "https://medium.com/test-article",
            "title": "Test Article",
            "summary": "This is a test summary."
        }
        
        result = lambda_handler(event, None)
        
        assert result["statusCode"] == 500
        assert "Secret not found" in result["body"]["message"]
        mock_send_notification.assert_called_once()
    
    @patch('lambdas.send_to_slack.send_webhook_request')
    @patch('lambdas.send_to_slack.get_slack_webhook_url')
    @patch('lambdas.send_to_slack.send_admin_notification')
    def test_lambda_handler_webhook_network_error(self, mock_send_notification, mock_get_webhook, mock_send_webhook):
        """Test error handling for webhook network errors."""
        # Mock dependencies
        mock_get_webhook.return_value = "https://hooks.slack.com/services/test/webhook"
        mock_send_webhook.side_effect = NetworkError("Connection failed")
        
        event = {
            "url": "https://medium.com/test-article",
            "title": "Test Article",
            "summary": "This is a test summary."
        }
        
        result = lambda_handler(event, None)
        
        assert result["statusCode"] == 500
        assert "Connection failed" in result["body"]["message"]
        mock_send_notification.assert_called_once()
    
    @patch('lambdas.send_to_slack.send_webhook_request')
    @patch('lambdas.send_to_slack.get_slack_webhook_url')
    @patch('lambdas.send_to_slack.send_admin_notification')
    def test_lambda_handler_webhook_validation_error(self, mock_send_notification, mock_get_webhook, mock_send_webhook):
        """Test error handling for webhook validation errors."""
        # Mock dependencies
        mock_get_webhook.return_value = "https://hooks.slack.com/services/test/webhook"
        mock_send_webhook.side_effect = ValidationError("Invalid webhook URL")
        
        event = {
            "url": "https://medium.com/test-article",
            "title": "Test Article",
            "summary": "This is a test summary."
        }
        
        result = lambda_handler(event, None)
        
        assert result["statusCode"] == 500
        assert "Invalid webhook URL" in result["body"]["message"]
        mock_send_notification.assert_called_once()
    
    @patch('lambdas.send_to_slack.get_slack_webhook_url')
    @patch('lambdas.send_to_slack.send_admin_notification')
    def test_lambda_handler_unexpected_error(self, mock_send_notification, mock_get_webhook):
        """Test error handling for unexpected errors."""
        # Mock unexpected error
        mock_get_webhook.side_effect = Exception("Unexpected error")
        
        event = {
            "url": "https://medium.com/test-article",
            "title": "Test Article",
            "summary": "This is a test summary."
        }
        
        result = lambda_handler(event, None)
        
        assert result["statusCode"] == 500
        assert "Unexpected error" in result["body"]["message"]
        mock_send_notification.assert_called_once()
    
    @patch('lambdas.send_to_slack.send_webhook_request')
    @patch('lambdas.send_to_slack.get_slack_webhook_url')
    def test_lambda_handler_with_complex_article_data(self, mock_get_webhook, mock_send_webhook):
        """Test processing with complex article data including special characters."""
        # Mock dependencies
        mock_get_webhook.return_value = "https://hooks.slack.com/services/test/webhook"
        mock_send_webhook.return_value = {"success": True, "status_code": 200}
        
        # Test event with complex data
        event = {
            "url": "https://medium.com/@author/complex-article-title-123",
            "title": "Complex Article: *Bold* and _Italic_ Text",
            "summary": "This summary contains special characters: @#$%^&*() and emojis 🚀✨",
            "content": "Full article content (should be ignored)"
        }
        
        result = lambda_handler(event, None)
        
        assert result["statusCode"] == 200
        assert result["body"]["success"] is True
        
        # Verify the formatted message includes special characters correctly
        expected_message = "📌 *Complex Article: *Bold* and _Italic_ Text*\n\n📝 This summary contains special characters: @#$%^&*() and emojis 🚀✨\n\n🔗 link：https://medium.com/@author/complex-article-title-123"
        mock_send_webhook.assert_called_once_with(
            "https://hooks.slack.com/services/test/webhook",
            {"summary": expected_message}
        )


class TestIntegration:
    """Integration test cases."""
    
    @patch('lambdas.send_to_slack.requests.post')
    @patch('lambdas.send_to_slack.get_slack_webhook_url')
    def test_end_to_end_processing(self, mock_get_webhook, mock_post):
        """Test complete end-to-end processing flow."""
        # Mock dependencies
        mock_get_webhook.return_value = "https://hooks.slack.com/services/test/webhook"
        mock_response = Mock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response
        
        # Test complete flow
        event = {
            "url": "https://medium.com/test-article",
            "title": "Integration Test Article",
            "summary": "This is an integration test summary."
        }
        
        result = lambda_handler(event, None)
        
        # Verify successful processing
        assert result["statusCode"] == 200
        assert result["body"]["success"] is True
        assert result["body"]["article_title"] == "Integration Test Article"
        
        # Verify webhook was called correctly
        expected_message = "📌 *Integration Test Article*\n\n📝 This is an integration test summary.\n\n🔗 link：https://medium.com/test-article"
        mock_post.assert_called_once_with(
            "https://hooks.slack.com/services/test/webhook",
            json={"summary": expected_message},
            headers={'Content-Type': 'application/json'},
            timeout=30
        )