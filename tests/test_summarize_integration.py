"""
Integration tests for the Summarize Lambda function.
"""
import json
import pytest
from unittest.mock import Mock, patch

from lambdas.summarize import lambda_handler
from shared.models import Article


class TestSummarizeIntegration:
    """Integration test cases for the Summarize Lambda function."""
    
    @patch('lambdas.summarize.create_lambda_logger')
    @patch('lambdas.summarize.bedrock_client')
    def test_end_to_end_summarization_success(self, mock_client, mock_create_logger):
        """Test complete end-to-end summarization process."""
        # Arrange
        mock_response = {
            'output': {
                'message': {
                    'content': [
                        {
                            'text': 'This article discusses the latest trends in artificial intelligence and machine learning, highlighting key developments in natural language processing and computer vision. The author emphasizes the importance of ethical AI development and responsible deployment of these technologies.'
                        }
                    ]
                }
            }
        }
        mock_client.converse.return_value = mock_response
        mock_logger = Mock()
        mock_create_logger.return_value = mock_logger
        
        event = {
            "url": "https://medium.com/@author/ai-trends-2024",
            "title": "The Future of AI: Trends and Predictions for 2024",
            "content": """
            Artificial intelligence continues to evolve at an unprecedented pace, with 2024 marking a pivotal year for the industry. 
            From breakthrough developments in large language models to revolutionary advances in computer vision, the AI landscape 
            is transforming rapidly. This article explores the key trends that are shaping the future of artificial intelligence.
            
            Natural Language Processing has seen remarkable improvements, with models becoming more sophisticated and capable of 
            understanding context and nuance. The integration of AI into everyday applications has become seamless, making 
            technology more accessible to users worldwide.
            
            Computer vision technologies have also made significant strides, enabling more accurate object recognition and 
            real-time image processing. These advances have applications across industries, from healthcare to autonomous vehicles.
            
            However, with great power comes great responsibility. The ethical implications of AI development cannot be ignored. 
            As we advance these technologies, we must ensure they are developed and deployed responsibly, with consideration for 
            privacy, bias, and societal impact.
            
            Looking ahead, the future of AI appears bright, with continued innovation expected across all domains. The key will be 
            balancing technological advancement with ethical considerations to create AI systems that benefit humanity as a whole.
            """,
            "summary": ""
        }
        context = Mock()
        
        # Act
        result = lambda_handler(event, context)
        
        # Assert
        assert result["url"] == "https://medium.com/@author/ai-trends-2024"
        assert result["title"] == "The Future of AI: Trends and Predictions for 2024"
        assert result["summary"] != ""
        assert "artificial intelligence" in result["summary"].lower()
        assert len(result["summary"]) > 50  # Ensure it's a meaningful summary
        
        # Verify Bedrock was called with correct parameters
        mock_client.converse.assert_called_once()
        call_args = mock_client.converse.call_args
        assert call_args[1]['modelId'] == "amazon.nova-pro-v1:0"
        assert call_args[1]['inferenceConfig']['maxTokens'] == 500
        assert call_args[1]['inferenceConfig']['temperature'] == 0.3
    
    @patch('lambdas.summarize.create_lambda_logger')
    @patch('lambdas.summarize.bedrock_client')
    def test_end_to_end_with_long_content_truncation(self, mock_client, mock_create_logger):
        """Test summarization with content that requires truncation."""
        # Arrange
        mock_response = {
            'output': {
                'message': {
                    'content': [
                        {
                            'text': 'This is a summary of the truncated long article content.'
                        }
                    ]
                }
            }
        }
        mock_client.converse.return_value = mock_response
        mock_logger = Mock()
        mock_create_logger.return_value = mock_logger
        
        # Create very long content (over 3000 characters)
        long_content = "This is a very long article. " * 200  # Creates ~6000 characters
        
        event = {
            "url": "https://medium.com/@author/long-article",
            "title": "A Very Long Article",
            "content": long_content,
            "summary": ""
        }
        context = Mock()
        
        # Act
        result = lambda_handler(event, context)
        
        # Assert
        assert result["summary"] == "This is a summary of the truncated long article content."
        
        # Verify that the content was truncated in the prompt
        call_args = mock_client.converse.call_args
        prompt = call_args[1]['messages'][0]['content'][0]['text']
        assert "..." in prompt  # Indicates truncation occurred
    
    @patch('lambdas.summarize.create_lambda_logger')
    @patch('lambdas.summarize.bedrock_client')
    def test_end_to_end_with_api_failure_and_fallback(self, mock_client, mock_create_logger):
        """Test complete flow when Bedrock API fails and fallback is used."""
        # Arrange
        mock_client.converse.side_effect = Exception("Bedrock service unavailable")
        mock_logger = Mock()
        mock_create_logger.return_value = mock_logger
        
        event = {
            "url": "https://medium.com/@author/test-article",
            "title": "Test Article for Fallback",
            "content": "This is test content that will trigger a fallback summary.",
            "summary": ""
        }
        context = Mock()
        
        # Act
        result = lambda_handler(event, context)
        
        # Assert
        assert result["url"] == "https://medium.com/@author/test-article"
        assert result["title"] == "Test Article for Fallback"
        assert result["summary"] == "Summary unavailable for 'Test Article for Fallback'. The article content could not be processed at this time."
    
    @patch('lambdas.summarize.create_lambda_logger')
    @patch('lambdas.summarize.bedrock_client')
    def test_end_to_end_with_empty_bedrock_response(self, mock_client, mock_create_logger):
        """Test complete flow when Bedrock returns empty response."""
        # Arrange
        mock_response = {
            'output': {
                'message': {
                    'content': [
                        {
                            'text': ''  # Empty response
                        }
                    ]
                }
            }
        }
        mock_client.converse.return_value = mock_response
        mock_logger = Mock()
        mock_create_logger.return_value = mock_logger
        
        event = {
            "url": "https://medium.com/@author/empty-response-test",
            "title": "Empty Response Test",
            "content": "This content will result in an empty response from Bedrock.",
            "summary": ""
        }
        context = Mock()
        
        # Act
        result = lambda_handler(event, context)
        
        # Assert
        assert result["summary"] == "Summary unavailable for 'Empty Response Test'. The article content could not be processed at this time."
    
    def test_end_to_end_with_article_model_integration(self):
        """Test integration with Article data model."""
        # Arrange
        article_data = {
            "url": "https://medium.com/@author/model-test",
            "title": "Article Model Test",
            "content": "Testing Article model integration.",
            "summary": ""
        }
        
        # Create Article object to verify model compatibility
        article = Article.from_dict(article_data)
        
        # Act & Assert
        assert article.url == "https://medium.com/@author/model-test"
        assert article.title == "Article Model Test"
        assert article.content == "Testing Article model integration."
        assert article.summary == ""
        
        # Test conversion back to dict
        result_dict = article.to_dict()
        assert result_dict == article_data
    
    @patch('lambdas.summarize.create_lambda_logger')
    @patch('lambdas.summarize.bedrock_client')
    def test_end_to_end_with_special_characters(self, mock_client, mock_create_logger):
        """Test summarization with special characters in content."""
        # Arrange
        mock_response = {
            'output': {
                'message': {
                    'content': [
                        {
                            'text': 'Summary of article with special characters and formatting.'
                        }
                    ]
                }
            }
        }
        mock_client.converse.return_value = mock_response
        mock_logger = Mock()
        mock_create_logger.return_value = mock_logger
        
        event = {
            "url": "https://medium.com/@author/special-chars",
            "title": "Article with Special Characters: 'Quotes' & \"More Quotes\"",
            "content": """
            This article contains various special characters:
            - Quotes: 'single' and "double"
            - Symbols: @#$%^&*()
            - Unicode: café, naïve, résumé
            - HTML entities: &amp; &lt; &gt;
            - Emojis: 🚀 💡 🎯
            
            The content should be properly handled by the summarization process.
            """,
            "summary": ""
        }
        context = Mock()
        
        # Act
        result = lambda_handler(event, context)
        
        # Assert
        assert result["title"] == "Article with Special Characters: 'Quotes' & \"More Quotes\""
        assert result["summary"] == "Summary of article with special characters and formatting."
        
        # Verify the prompt was properly formatted
        call_args = mock_client.converse.call_args
        prompt = call_args[1]['messages'][0]['content'][0]['text']
        assert "Article with Special Characters" in prompt
        assert "café" in prompt
    
    @patch('lambdas.summarize.create_lambda_logger')
    @patch('lambdas.summarize.bedrock_client')
    def test_end_to_end_performance_simulation(self, mock_client, mock_create_logger):
        """Test performance characteristics with realistic content size."""
        # Arrange
        mock_response = {
            'output': {
                'message': {
                    'content': [
                        {
                            'text': 'This comprehensive summary covers cloud computing fundamentals, including IaaS, PaaS, and SaaS service models, security considerations, and cost optimization strategies for modern organizations.'
                        }
                    ]
                }
            }
        }
        mock_client.converse.return_value = mock_response
        mock_logger = Mock()
        mock_create_logger.return_value = mock_logger
        
        # Create realistic article content (around 2000 characters)
        realistic_content = """
        Cloud computing has revolutionized the way businesses operate, offering unprecedented scalability, 
        flexibility, and cost-effectiveness. As organizations continue to migrate their operations to the cloud, 
        understanding the key principles and best practices becomes crucial for success.
        
        The three main service models - Infrastructure as a Service (IaaS), Platform as a Service (PaaS), 
        and Software as a Service (SaaS) - each offer unique advantages depending on the organization's needs. 
        IaaS provides the fundamental computing resources, while PaaS offers a platform for application 
        development and deployment. SaaS delivers complete software solutions over the internet.
        
        Security remains a top concern for cloud adoption. Organizations must implement robust security 
        measures including encryption, access controls, and regular security audits. The shared responsibility 
        model means that while cloud providers secure the infrastructure, customers are responsible for 
        securing their data and applications.
        
        Cost optimization is another critical aspect of cloud management. Organizations should regularly 
        review their resource usage, implement auto-scaling policies, and take advantage of reserved 
        instances and spot pricing to minimize costs while maintaining performance.
        
        Looking forward, emerging technologies like serverless computing, edge computing, and AI-driven 
        cloud services are set to further transform the landscape. Organizations that stay ahead of these 
        trends will be better positioned to leverage the full potential of cloud computing.
        """
        
        event = {
            "url": "https://medium.com/@author/cloud-computing-guide",
            "title": "The Complete Guide to Cloud Computing in 2024",
            "content": realistic_content,
            "summary": ""
        }
        context = Mock()
        
        # Act
        result = lambda_handler(event, context)
        
        # Assert
        assert result["summary"] != ""
        assert len(result["summary"]) > 100  # Ensure substantial summary
        assert "cloud" in result["summary"].lower() or "computing" in result["summary"].lower()
        
        # Verify API call was made with reasonable parameters
        mock_client.converse.assert_called_once()
        call_args = mock_client.converse.call_args
        assert len(call_args[1]['messages'][0]['content'][0]['text']) > 1000  # Substantial prompt


if __name__ == '__main__':
    pytest.main([__file__])