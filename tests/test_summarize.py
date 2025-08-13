"""
Unit tests for the Summarize Lambda function.
"""
import json
import pytest
from unittest.mock import Mock, patch, MagicMock
from botocore.exceptions import ClientError

from lambdas.summarize import (
    lambda_handler,
    generate_summary,
    format_prompt,
    extract_summary_from_response,
    generate_fallback_summary
)
from shared.error_handling import RetryableError, FatalError, ValidationError


class TestLambdaHandler:
    """Test cases for the lambda_handler function."""
    
    @patch('lambdas.summarize.create_lambda_logger')
    def test_lambda_handler_success(self, mock_create_logger):
        """Test successful lambda handler execution."""
        # Arrange
        event = {
            "url": "https://medium.com/test-article",
            "title": "Test Article",
            "content": "This is test content for summarization.",
            "summary": ""
        }
        context = Mock()
        mock_logger = Mock()
        mock_create_logger.return_value = mock_logger
        
        with patch('lambdas.summarize.generate_summary') as mock_generate:
            mock_generate.return_value = "This is a test summary."
            
            # Act
            result = lambda_handler(event, context)
            
            # Assert
            assert result["url"] == "https://medium.com/test-article"
            assert result["title"] == "Test Article"
            assert result["content"] == "This is test content for summarization."
            assert result["summary"] == "This is a test summary."
            # Check that generate_summary was called with the right arguments (content, title, logger, tracker)
            assert mock_generate.call_count == 1
            call_args = mock_generate.call_args[0]
            assert call_args[0] == "This is test content for summarization."
            assert call_args[1] == "Test Article"
    
    @patch('lambdas.summarize.create_lambda_logger')
    def test_lambda_handler_invalid_input_type(self, mock_create_logger):
        """Test lambda handler with invalid input type."""
        # Arrange
        event = "invalid_string_input"
        context = Mock()
        mock_logger = Mock()
        mock_create_logger.return_value = mock_logger
        
        # Act & Assert
        with pytest.raises(ValidationError, match="Invalid input: expected dictionary"):
            lambda_handler(event, context)
    
    @patch('lambdas.summarize.create_lambda_logger')
    def test_lambda_handler_missing_title(self, mock_create_logger):
        """Test lambda handler with missing title."""
        # Arrange
        event = {
            "url": "https://medium.com/test-article",
            "title": "",
            "content": "This is test content.",
            "summary": ""
        }
        context = Mock()
        mock_logger = Mock()
        mock_create_logger.return_value = mock_logger
        
        # Act & Assert
        with pytest.raises(ValidationError, match="Article title and content are required"):
            lambda_handler(event, context)
    
    @patch('lambdas.summarize.create_lambda_logger')
    def test_lambda_handler_missing_content(self, mock_create_logger):
        """Test lambda handler with missing content."""
        # Arrange
        event = {
            "url": "https://medium.com/test-article",
            "title": "Test Article",
            "content": "",
            "summary": ""
        }
        context = Mock()
        mock_logger = Mock()
        mock_create_logger.return_value = mock_logger
        
        # Act & Assert
        with pytest.raises(ValidationError, match="Article title and content are required"):
            lambda_handler(event, context)
    
    @patch('lambdas.summarize.create_lambda_logger')
    def test_lambda_handler_generate_summary_failure(self, mock_create_logger):
        """Test lambda handler when summary generation fails."""
        # Arrange
        event = {
            "url": "https://medium.com/test-article",
            "title": "Test Article",
            "content": "This is test content.",
            "summary": ""
        }
        context = Mock()
        mock_logger = Mock()
        mock_create_logger.return_value = mock_logger
        
        with patch('lambdas.summarize.generate_summary') as mock_generate:
            mock_generate.side_effect = Exception("Summary generation failed")
            
            # Act & Assert
            with pytest.raises(Exception, match="Summary generation failed"):
                lambda_handler(event, context)


class TestGenerateSummary:
    """Test cases for the generate_summary function."""
    
    @patch('lambdas.summarize.bedrock_client')
    def test_generate_summary_success(self, mock_client):
        """Test successful summary generation."""
        # Arrange
        mock_response = {
            'output': {
                'message': {
                    'content': [
                        {
                            'text': 'This is a generated summary of the article content.'
                        }
                    ]
                }
            }
        }
        mock_client.converse.return_value = mock_response
        
        content = "This is a long article about technology and innovation."
        title = "Tech Innovation Article"
        mock_logger = Mock()
        mock_tracker = Mock()
        
        # Act
        result = generate_summary(content, title, mock_logger, mock_tracker)
        
        # Assert
        assert result == "This is a generated summary of the article content."
        mock_client.converse.assert_called_once()
        
        # Verify the call arguments
        call_args = mock_client.converse.call_args
        assert call_args[1]['modelId'] == "amazon.nova-pro-v1:0"
        assert 'messages' in call_args[1]
        assert 'inferenceConfig' in call_args[1]
        assert call_args[1]['inferenceConfig']['maxTokens'] == 500
        assert call_args[1]['inferenceConfig']['temperature'] == 0.3
    
    @patch('lambdas.summarize.bedrock_client')
    def test_generate_summary_empty_response(self, mock_client):
        """Test summary generation with empty response."""
        # Arrange
        mock_response = {
            'output': {
                'message': {
                    'content': [
                        {
                            'text': ''
                        }
                    ]
                }
            }
        }
        mock_client.converse.return_value = mock_response
        
        content = "Test content"
        title = "Test Title"
        mock_logger = Mock()
        mock_tracker = Mock()
        
        # Act
        result = generate_summary(content, title, mock_logger, mock_tracker)
        
        # Assert
        assert result == "Summary unavailable for 'Test Title'. The article content could not be processed at this time."
    
    @patch('lambdas.summarize.bedrock_client')
    def test_generate_summary_throttling_error(self, mock_client):
        """Test summary generation with throttling error."""
        # Arrange
        error_response = {
            'Error': {
                'Code': 'ThrottlingException',
                'Message': 'Request was throttled'
            }
        }
        mock_client.converse.side_effect = ClientError(error_response, 'converse')
        
        content = "Test content"
        title = "Test Title"
        mock_logger = Mock()
        mock_tracker = Mock()
        
        # Act & Assert
        with pytest.raises(RetryableError, match="Bedrock API retryable error"):
            generate_summary(content, title, mock_logger, mock_tracker)
    
    @patch('lambdas.summarize.bedrock_client')
    def test_generate_summary_validation_error(self, mock_client):
        """Test summary generation with validation error."""
        # Arrange
        error_response = {
            'Error': {
                'Code': 'ValidationException',
                'Message': 'Invalid request parameters'
            }
        }
        mock_client.converse.side_effect = ClientError(error_response, 'converse')
        
        content = "Test content"
        title = "Test Title"
        mock_logger = Mock()
        mock_tracker = Mock()
        
        # Act & Assert
        with pytest.raises(FatalError, match="Bedrock API fatal error"):
            generate_summary(content, title, mock_logger, mock_tracker)
    
    @patch('lambdas.summarize.bedrock_client')
    def test_generate_summary_access_denied_error(self, mock_client):
        """Test summary generation with access denied error."""
        # Arrange
        error_response = {
            'Error': {
                'Code': 'AccessDeniedException',
                'Message': 'Access denied to model'
            }
        }
        mock_client.converse.side_effect = ClientError(error_response, 'converse')
        
        content = "Test content"
        title = "Test Title"
        mock_logger = Mock()
        mock_tracker = Mock()
        
        # Act & Assert
        with pytest.raises(FatalError, match="Bedrock API fatal error"):
            generate_summary(content, title, mock_logger, mock_tracker)
    
    @patch('lambdas.summarize.bedrock_client')
    def test_generate_summary_unknown_error(self, mock_client):
        """Test summary generation with unknown error."""
        # Arrange
        error_response = {
            'Error': {
                'Code': 'UnknownException',
                'Message': 'Unknown error occurred'
            }
        }
        mock_client.converse.side_effect = ClientError(error_response, 'converse')
        
        content = "Test content"
        title = "Test Title"
        mock_logger = Mock()
        mock_tracker = Mock()
        
        # Act & Assert
        with pytest.raises(RetryableError, match="Bedrock API unknown error"):
            generate_summary(content, title, mock_logger, mock_tracker)
    
    @patch('lambdas.summarize.bedrock_client')
    @patch('lambdas.summarize.generate_fallback_summary')
    def test_generate_summary_unexpected_error_with_fallback(self, mock_fallback, mock_client):
        """Test summary generation with unexpected error and fallback."""
        # Arrange
        mock_client.converse.side_effect = Exception("Unexpected error")
        mock_fallback.return_value = "Fallback summary"
        
        content = "Test content"
        title = "Test Title"
        mock_logger = Mock()
        mock_tracker = Mock()
        
        # Act
        result = generate_summary(content, title, mock_logger, mock_tracker)
        
        # Assert
        assert result == "Fallback summary"
        mock_fallback.assert_called_once_with("Test Title")
    
    @patch('lambdas.summarize.bedrock_client')
    @patch('lambdas.summarize.generate_fallback_summary')
    def test_generate_summary_unexpected_error_fallback_fails(self, mock_fallback, mock_client):
        """Test summary generation when both main and fallback fail."""
        # Arrange
        mock_client.converse.side_effect = Exception("Unexpected error")
        mock_fallback.side_effect = Exception("Fallback failed")
        
        content = "Test content"
        title = "Test Title"
        mock_logger = Mock()
        mock_tracker = Mock()
        
        # Act & Assert
        with pytest.raises(RetryableError, match="Summary generation failed"):
            generate_summary(content, title, mock_logger, mock_tracker)


class TestFormatPrompt:
    """Test cases for the format_prompt function."""
    
    def test_format_prompt_normal_content(self):
        """Test prompt formatting with normal content length."""
        # Arrange
        content = "This is a test article about technology and innovation in the modern world."
        title = "Technology Innovation"
        
        # Act
        result = format_prompt(content, title)
        
        # Assert
        assert "Technology Innovation" in result
        assert content in result
        assert "Please provide a concise and informative summary" in result
        assert "Instructions:" in result
        assert "Summary:" in result
    
    def test_format_prompt_long_content(self):
        """Test prompt formatting with content that needs truncation."""
        # Arrange
        content = "A" * 4000  # Content longer than 3000 characters
        title = "Long Article"
        
        # Act
        result = format_prompt(content, title)
        
        # Assert
        assert "Long Article" in result
        assert "A" * 3000 + "..." in result
        assert len([line for line in result.split('\n') if 'A' in line][0]) <= 3003  # 3000 + "..."
    
    def test_format_prompt_empty_content(self):
        """Test prompt formatting with empty content."""
        # Arrange
        content = ""
        title = "Empty Article"
        
        # Act
        result = format_prompt(content, title)
        
        # Assert
        assert "Empty Article" in result
        assert "Article Content:\n\n" in result


class TestExtractSummaryFromResponse:
    """Test cases for the extract_summary_from_response function."""
    
    def test_extract_summary_success(self):
        """Test successful summary extraction."""
        # Arrange
        response = {
            'output': {
                'message': {
                    'content': [
                        {
                            'text': 'This is the extracted summary.'
                        }
                    ]
                }
            }
        }
        
        # Act
        result = extract_summary_from_response(response)
        
        # Assert
        assert result == "This is the extracted summary."
    
    def test_extract_summary_with_whitespace(self):
        """Test summary extraction with whitespace."""
        # Arrange
        response = {
            'output': {
                'message': {
                    'content': [
                        {
                            'text': '  \n  This is the extracted summary.  \n  '
                        }
                    ]
                }
            }
        }
        
        # Act
        result = extract_summary_from_response(response)
        
        # Assert
        assert result == "This is the extracted summary."
    
    def test_extract_summary_empty_content(self):
        """Test summary extraction with empty content."""
        # Arrange
        response = {
            'output': {
                'message': {
                    'content': []
                }
            }
        }
        
        # Act
        result = extract_summary_from_response(response)
        
        # Assert
        assert result == ""
    
    def test_extract_summary_missing_output(self):
        """Test summary extraction with missing output."""
        # Arrange
        response = {}
        
        # Act
        result = extract_summary_from_response(response)
        
        # Assert
        assert result == ""
    
    def test_extract_summary_missing_message(self):
        """Test summary extraction with missing message."""
        # Arrange
        response = {
            'output': {}
        }
        
        # Act
        result = extract_summary_from_response(response)
        
        # Assert
        assert result == ""
    
    def test_extract_summary_invalid_structure(self):
        """Test summary extraction with invalid response structure."""
        # Arrange
        response = {
            'output': {
                'message': {
                    'content': [
                        {
                            'invalid_key': 'This should not be extracted'
                        }
                    ]
                }
            }
        }
        
        # Act
        result = extract_summary_from_response(response)
        
        # Assert
        assert result == ""
    
    def test_extract_summary_exception_handling(self):
        """Test summary extraction with exception in processing."""
        # Arrange
        response = None  # This will cause an exception
        
        # Act
        result = extract_summary_from_response(response)
        
        # Assert
        assert result == ""


class TestGenerateFallbackSummary:
    """Test cases for the generate_fallback_summary function."""
    
    def test_generate_fallback_summary(self):
        """Test fallback summary generation."""
        # Arrange
        title = "Test Article Title"
        
        # Act
        result = generate_fallback_summary(title)
        
        # Assert
        expected = "Summary unavailable for 'Test Article Title'. The article content could not be processed at this time."
        assert result == expected
    
    def test_generate_fallback_summary_empty_title(self):
        """Test fallback summary generation with empty title."""
        # Arrange
        title = ""
        
        # Act
        result = generate_fallback_summary(title)
        
        # Assert
        expected = "Summary unavailable for ''. The article content could not be processed at this time."
        assert result == expected
    
    def test_generate_fallback_summary_special_characters(self):
        """Test fallback summary generation with special characters in title."""
        # Arrange
        title = "Test Article: 'Special' & \"Quotes\""
        
        # Act
        result = generate_fallback_summary(title)
        
        # Assert
        expected = "Summary unavailable for 'Test Article: 'Special' & \"Quotes\"'. The article content could not be processed at this time."
        assert result == expected


class TestRetryBehavior:
    """Test cases for retry behavior with mocked decorators."""
    
    @patch('lambdas.summarize.bedrock_client')
    def test_retry_behavior_success_after_failure(self, mock_client):
        """Test that retry decorator works correctly."""
        # Arrange
        error_response = {
            'Error': {
                'Code': 'ThrottlingException',
                'Message': 'Request was throttled'
            }
        }
        success_response = {
            'output': {
                'message': {
                    'content': [
                        {
                            'text': 'Success after retry'
                        }
                    ]
                }
            }
        }
        
        # First call fails, second succeeds
        mock_client.converse.side_effect = [
            ClientError(error_response, 'converse'),
            success_response
        ]
        
        content = "Test content"
        title = "Test Title"
        mock_logger = Mock()
        mock_tracker = Mock()
        
        # Act
        with patch('time.sleep'):  # Mock sleep to speed up test
            result = generate_summary(content, title, mock_logger, mock_tracker)
        
        # Assert
        assert result == "Success after retry"
        assert mock_client.converse.call_count == 2


if __name__ == '__main__':
    pytest.main([__file__])