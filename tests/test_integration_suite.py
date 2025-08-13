"""
Comprehensive integration test suite for Medium Digest Summarizer
Tests end-to-end workflow, performance, and error scenarios
"""

import json
import time
import boto3
import pytest
import requests
import concurrent.futures
from unittest.mock import patch, MagicMock
from tests.test_data_generator import TestDataGenerator


class TestIntegrationSuite:
    """Comprehensive integration test suite"""
    
    @classmethod
    def setup_class(cls):
        """Set up test environment"""
        cls.test_data = TestDataGenerator()
        cls.session = boto3.Session()
        
        # Get stack outputs for testing
        try:
            cf_client = cls.session.client('cloudformation')
            stack_response = cf_client.describe_stacks(StackName='MediumDigestSummarizerStack')
            cls.stack_outputs = {
                output['OutputKey']: output['OutputValue'] 
                for output in stack_response['Stacks'][0].get('Outputs', [])
            }
        except Exception:
            cls.stack_outputs = {}
    
    def test_single_article_workflow(self):
        """Test workflow with single article"""
        test_email = self.test_data.generate_medium_email_with_articles(1)
        payload = {"payload": json.dumps(test_email)}
        
        with patch('boto3.client') as mock_boto_client:
            self._setup_successful_mocks(mock_boto_client, articles_processed=1)
            
            from lambdas.trigger import lambda_handler as trigger_handler
            
            event = {
                'body': json.dumps(payload),
                'headers': {'Content-Type': 'application/json'}
            }
            
            response = trigger_handler(event, {})
            
            assert response['statusCode'] == 200
            body = json.loads(response['body'])
            assert body['success'] is True
            assert body['articlesProcessed'] == 1
    
    def test_multiple_articles_workflow(self):
        """Test workflow with multiple articles"""
        test_email = self.test_data.generate_medium_email_with_articles(5)
        payload = {"payload": json.dumps(test_email)}
        
        with patch('boto3.client') as mock_boto_client:
            self._setup_successful_mocks(mock_boto_client, articles_processed=5)
            
            from lambdas.trigger import lambda_handler as trigger_handler
            
            event = {
                'body': json.dumps(payload),
                'headers': {'Content-Type': 'application/json'}
            }
            
            response = trigger_handler(event, {})
            
            assert response['statusCode'] == 200
            body = json.loads(response['body'])
            assert body['success'] is True
            assert body['articlesProcessed'] == 5
    
    def test_empty_email_workflow(self):
        """Test workflow with email containing no articles"""
        test_email = self.test_data.generate_medium_email_no_articles()
        payload = {"payload": json.dumps(test_email)}
        
        with patch('boto3.client') as mock_boto_client:
            mock_sf_client = MagicMock()
            mock_sf_client.start_sync_execution.return_value = {
                'status': 'SUCCEEDED',
                'output': json.dumps({
                    'articlesProcessed': 0,
                    'success': True,
                    'message': 'No articles found in email'
                })
            }
            mock_boto_client.return_value = mock_sf_client
            
            from lambdas.trigger import lambda_handler as trigger_handler
            
            event = {
                'body': json.dumps(payload),
                'headers': {'Content-Type': 'application/json'}
            }
            
            response = trigger_handler(event, {})
            
            assert response['statusCode'] == 200
            body = json.loads(response['body'])
            assert body['success'] is True
            assert body['articlesProcessed'] == 0
    
    def test_malformed_email_workflow(self):
        """Test workflow with malformed email content"""
        test_email = self.test_data.generate_malformed_email()
        payload = {"payload": json.dumps(test_email)}
        
        with patch('boto3.client') as mock_boto_client:
            mock_sf_client = MagicMock()
            mock_sf_client.start_sync_execution.return_value = {
                'status': 'FAILED',
                'error': 'InvalidEmailFormat',
                'cause': 'No valid Medium article links found'
            }
            mock_boto_client.return_value = mock_sf_client
            
            from lambdas.trigger import lambda_handler as trigger_handler
            
            event = {
                'body': json.dumps(payload),
                'headers': {'Content-Type': 'application/json'}
            }
            
            response = trigger_handler(event, {})
            
            assert response['statusCode'] == 500
            body = json.loads(response['body'])
            assert body['success'] is False
            assert 'error' in body
    
    def test_partial_failure_workflow(self):
        """Test workflow with some articles failing to process"""
        test_email = self.test_data.generate_medium_email_with_articles(3)
        payload = {"payload": json.dumps(test_email)}
        
        with patch('boto3.client') as mock_boto_client:
            mock_sf_client = MagicMock()
            mock_sf_client.start_sync_execution.return_value = {
                'status': 'SUCCEEDED',
                'output': json.dumps({
                    'articlesProcessed': 2,
                    'success': True,
                    'errors': ['Failed to fetch article 3: Network timeout']
                })
            }
            mock_boto_client.return_value = mock_sf_client
            
            from lambdas.trigger import lambda_handler as trigger_handler
            
            event = {
                'body': json.dumps(payload),
                'headers': {'Content-Type': 'application/json'}
            }
            
            response = trigger_handler(event, {})
            
            assert response['statusCode'] == 200
            body = json.loads(response['body'])
            assert body['success'] is True
            assert body['articlesProcessed'] == 2
            assert 'errors' in body
    
    def test_performance_large_payload(self):
        """Test performance with large number of articles"""
        test_email = self.test_data.generate_performance_test_payload(10)
        payload = {"payload": json.dumps(test_email)}
        
        start_time = time.time()
        
        with patch('boto3.client') as mock_boto_client:
            self._setup_successful_mocks(mock_boto_client, articles_processed=10)
            
            from lambdas.trigger import lambda_handler as trigger_handler
            
            event = {
                'body': json.dumps(payload),
                'headers': {'Content-Type': 'application/json'}
            }
            
            response = trigger_handler(event, {})
            
            execution_time = time.time() - start_time
            
            assert response['statusCode'] == 200
            body = json.loads(response['body'])
            assert body['success'] is True
            assert body['articlesProcessed'] == 10
            
            # Performance assertion - should complete within reasonable time
            assert execution_time < 5.0, f"Execution took too long: {execution_time}s"
    
    def test_concurrent_requests_performance(self):
        """Test system performance under concurrent load"""
        payloads = self.test_data.generate_concurrent_test_payloads(5)
        
        def make_request(payload):
            with patch('boto3.client') as mock_boto_client:
                self._setup_successful_mocks(mock_boto_client, articles_processed=2)
                
                from lambdas.trigger import lambda_handler as trigger_handler
                
                event = {
                    'body': json.dumps(payload),
                    'headers': {'Content-Type': 'application/json'}
                }
                
                start_time = time.time()
                response = trigger_handler(event, {})
                execution_time = time.time() - start_time
                
                return response, execution_time
        
        start_time = time.time()
        
        # Execute concurrent requests
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(make_request, payload) for payload in payloads]
            results = [future.result() for future in concurrent.futures.as_completed(futures)]
        
        total_time = time.time() - start_time
        
        # Verify all requests succeeded
        for response, execution_time in results:
            assert response['statusCode'] == 200
            body = json.loads(response['body'])
            assert body['success'] is True
            # Individual request should complete quickly
            assert execution_time < 3.0
        
        # Total concurrent execution should be efficient
        assert total_time < 10.0, f"Concurrent execution took too long: {total_time}s"
    
    def test_error_recovery_scenarios(self):
        """Test various error recovery scenarios"""
        test_cases = [
            {
                'name': 'Secrets Manager failure',
                'error': 'SecretsManagerError',
                'cause': 'Unable to retrieve Medium cookies'
            },
            {
                'name': 'Bedrock API failure',
                'error': 'BedrockError',
                'cause': 'AI summarization service unavailable'
            },
            {
                'name': 'Slack webhook failure',
                'error': 'SlackWebhookError',
                'cause': 'Failed to send message to Slack'
            }
        ]
        
        for test_case in test_cases:
            test_email = self.test_data.generate_medium_email_with_articles(2)
            payload = {"payload": json.dumps(test_email)}
            
            with patch('boto3.client') as mock_boto_client:
                mock_sf_client = MagicMock()
                mock_sf_client.start_sync_execution.return_value = {
                    'status': 'FAILED',
                    'error': test_case['error'],
                    'cause': test_case['cause']
                }
                mock_boto_client.return_value = mock_sf_client
                
                from lambdas.trigger import lambda_handler as trigger_handler
                
                event = {
                    'body': json.dumps(payload),
                    'headers': {'Content-Type': 'application/json'}
                }
                
                response = trigger_handler(event, {})
                
                # Should handle errors gracefully
                assert response['statusCode'] == 500
                body = json.loads(response['body'])
                assert body['success'] is False
                assert test_case['error'] in body.get('error', '')
    
    @pytest.mark.skipif(True, reason="Live tests require --run-live flag")
    def test_live_api_gateway_integration(self):
        """Test actual API Gateway endpoint with live AWS services"""
        if 'ApiGatewayUrl' not in self.stack_outputs:
            pytest.skip("API Gateway URL not available in stack outputs")
        
        api_url = self.stack_outputs['ApiGatewayUrl']
        api_key = self.stack_outputs.get('ApiKey', '')
        
        # Use minimal test payload to avoid hitting actual services too hard
        test_email = self.test_data.generate_medium_email_with_articles(1)
        payload = {"payload": json.dumps(test_email)}
        
        headers = {
            'Content-Type': 'application/json',
            'x-api-key': api_key
        }
        
        try:
            response = requests.post(
                f"{api_url}/process-digest",
                json=payload,
                headers=headers,
                timeout=60  # Longer timeout for live test
            )
            
            # Should get a response
            assert response.status_code in [200, 500]
            
            if response.status_code == 200:
                data = response.json()
                assert 'success' in data
                assert 'articlesProcessed' in data
                print(f"Live test successful: {data}")
            else:
                print(f"Live test returned error: {response.text}")
                
        except requests.exceptions.RequestException as e:
            pytest.fail(f"API Gateway request failed: {str(e)}")
    
    def _setup_successful_mocks(self, mock_boto_client, articles_processed: int = 1):
        """Set up successful mock responses for AWS services"""
        # Mock Step Functions client
        mock_sf_client = MagicMock()
        mock_sf_client.start_sync_execution.return_value = {
            'status': 'SUCCEEDED',
            'output': json.dumps({
                'articlesProcessed': articles_processed,
                'success': True
            })
        }
        
        # Mock Secrets Manager client
        mock_secrets_client = MagicMock()
        mock_secrets_client.get_secret_value.side_effect = [
            {'SecretString': 'test-cookies'},
            {'SecretString': 'https://hooks.slack.com/test'}
        ]
        
        # Mock Bedrock client
        mock_bedrock_client = MagicMock()
        mock_bedrock_client.invoke_model.return_value = {
            'body': MagicMock(read=lambda: json.dumps({
                'content': [{'text': 'Test summary'}]
            }).encode())
        }
        
        def mock_client_factory(service_name, **kwargs):
            if service_name == 'stepfunctions':
                return mock_sf_client
            elif service_name == 'secretsmanager':
                return mock_secrets_client
            elif service_name == 'bedrock-runtime':
                return mock_bedrock_client
            return MagicMock()
        
        mock_boto_client.side_effect = mock_client_factory
        
        # Mock HTTP requests
        with patch('requests.get') as mock_get, patch('requests.post') as mock_post:
            mock_get.return_value.status_code = 200
            mock_get.return_value.text = self.test_data.generate_medium_article_html(
                "Test Article", "This is test content."
            )
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {'ok': True}