"""
Integration tests for the Trigger Lambda function.
"""
import json
import os
import pytest
from unittest.mock import Mock, patch, MagicMock
from botocore.exceptions import ClientError

# Import the module under test
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from lambdas.trigger import lambda_handler


def create_mock_context():
    """Create a mock Lambda context with proper string attributes."""
    context = Mock()
    context.aws_request_id = 'test-request-123'
    context.function_name = 'test-trigger-function'
    context.function_version = '$LATEST'
    context.invoked_function_arn = 'arn:aws:lambda:us-east-1:123456789012:function:test-trigger-function'
    context.memory_limit_in_mb = '256'
    context.remaining_time_in_millis = Mock(return_value=30000)
    return context


@patch('lambdas.trigger.create_lambda_logger')
class TestTriggerLambdaIntegration:
    """Integration tests for the Trigger Lambda function."""
    
    @patch('lambdas.trigger.stepfunctions_client')
    @patch('lambdas.trigger.boto3.client')
    @patch.dict(os.environ, {'STATE_MACHINE_ARN': 'arn:aws:states:us-east-1:123456789012:stateMachine:medium-digest'})
    def test_real_medium_email_processing(self, mock_boto3_client, mock_stepfunctions, mock_logger):
        """Test processing a realistic Medium Daily Digest email."""
        # Setup logger mock
        mock_logger_instance = Mock()
        mock_logger.return_value = mock_logger_instance
        
        # Setup Step Functions mock
        mock_stepfunctions.start_sync_execution.return_value = {
            'executionArn': 'arn:aws:states:us-east-1:123456789012:execution:medium-digest:test-123',
            'status': 'SUCCEEDED'
        }
        
        # Realistic Medium Daily Digest email content
        email_html = '''
        <!DOCTYPE html>
        <html>
        <head>
            <title>Medium Daily Digest</title>
        </head>
        <body>
            <div class="digest-container">
                <h1>Your Daily Digest</h1>
                <div class="article-item">
                    <h2><a href="https://medium.com/@author/article-title-123">How to Build Better Software</a></h2>
                    <p>Learn the essential practices that separate good developers from great ones...</p>
                    <a href="https://medium.com/@author/article-title-123" class="read-more">Read more</a>
                </div>
                <div class="article-item">
                    <h2><a href="https://towardsdatascience.medium.com/machine-learning-guide-456">Machine Learning for Beginners</a></h2>
                    <p>A comprehensive introduction to ML concepts and practical applications...</p>
                    <a href="https://towardsdatascience.medium.com/machine-learning-guide-456" class="read-more">Read more</a>
                </div>
                <div class="footer">
                    <p>You're receiving this because you subscribed to Medium Daily Digest.</p>
                    <a href="https://medium.com/unsubscribe">Unsubscribe</a>
                </div>
            </div>
        </body>
        </html>
        '''
        
        # Mock S3 client
        mock_s3_client = Mock()
        mock_s3_client.get_object.return_value = {
            'Body': Mock(read=Mock(return_value=email_html.encode('utf-8')))
        }
        mock_boto3_client.return_value = mock_s3_client
        
        # S3 event (not API Gateway)
        event = {
            'Records': [
                {
                    'eventSource': 'aws:s3',
                    'eventName': 's3:ObjectCreated:Put',
                    's3': {
                        'bucket': {'name': 'medium-digest-emails'},
                        'object': {'key': 'daily-digest-2024-01-15.html'}
                    }
                }
            ]
        }
        
        context = create_mock_context()
        
        # Execute
        result = lambda_handler(event, context)
        
        # Verify response structure
        assert result['statusCode'] == 200
        
        # Verify response body
        body = result['body']
        assert body['message'] == 'S3 event processing completed successfully'
        assert body['processedRecords'] == 1
        assert 'executionTime' in body
        assert isinstance(body['executionTime'], (int, float))
        assert len(body['results']) == 1
        assert body['results'][0]['bucket'] == 'medium-digest-emails'
        assert body['results'][0]['key'] == 'daily-digest-2024-01-15.html'
        assert body['results'][0]['status'] == 'SUCCEEDED'
        
        # Verify S3 was called correctly
        mock_s3_client.get_object.assert_called_once_with(
            Bucket='medium-digest-emails', 
            Key='daily-digest-2024-01-15.html'
        )
        
        # Verify Step Functions was called correctly
        mock_stepfunctions.start_sync_execution.assert_called_once()
        call_args = mock_stepfunctions.start_sync_execution.call_args
        
        # Verify state machine ARN
        assert call_args[1]['stateMachineArn'] == 'arn:aws:states:us-east-1:123456789012:stateMachine:medium-digest'
        
        # Verify execution name format
        execution_name = call_args[1]['name']
        assert execution_name.startswith('medium-digest-')
        assert len(execution_name.split('-')) >= 3  # medium-digest-timestamp-random
        
        # Verify input format
        input_data = json.loads(call_args[1]['input'])
        assert 'payload' in input_data
        assert 'timestamp' in input_data
        assert input_data['source'] == 's3_event'
        assert input_data['payload'] == email_html
        assert 's3' in input_data
        assert input_data['s3']['bucket'] == 'medium-digest-emails'
        assert input_data['s3']['key'] == 'daily-digest-2024-01-15.html'
    
    @patch('lambdas.trigger.stepfunctions_client')
    @patch.dict(os.environ, {'STATE_MACHINE_ARN': 'arn:aws:states:us-east-1:123456789012:stateMachine:medium-digest'})
    def test_step_function_timeout_handling(self, mock_stepfunctions):
        """Test handling of Step Function timeout scenarios."""
        # Setup Step Functions mock to simulate timeout
        mock_stepfunctions.start_sync_execution.return_value = {
            'executionArn': 'arn:aws:states:us-east-1:123456789012:execution:medium-digest:timeout-123',
            'status': 'TIMED_OUT',
            'error': 'States.Timeout',
            'cause': 'The execution timed out after 300 seconds'
        }
        
        # Test event
        event = {
            'body': json.dumps({
                'payload': '<html><body><a href="https://medium.com/test">Test</a></body></html>'
            })
        }
        context = Mock()
        
        # Execute
        result = lambda_handler(event, context)
        
        # Should still return success since Step Function started successfully
        # The timeout is handled by the Step Function itself
        assert result['statusCode'] == 200
        body = json.loads(result['body'])
        assert body['status'] == 'TIMED_OUT'
    
    @patch('lambdas.trigger.stepfunctions_client')
    @patch.dict(os.environ, {'STATE_MACHINE_ARN': 'arn:aws:states:us-east-1:123456789012:stateMachine:medium-digest'})
    def test_step_function_execution_failure(self, mock_stepfunctions):
        """Test handling of Step Function execution failures."""
        # Setup Step Functions mock to simulate execution failure
        mock_stepfunctions.start_sync_execution.return_value = {
            'executionArn': 'arn:aws:states:us-east-1:123456789012:execution:medium-digest:failed-123',
            'status': 'FAILED',
            'error': 'States.TaskFailed',
            'cause': 'Lambda function returned error: Invalid Medium cookies'
        }
        
        # Test event
        event = {
            'body': json.dumps({
                'payload': '<html><body><a href="https://medium.com/test">Test</a></body></html>'
            })
        }
        context = Mock()
        
        # Execute
        result = lambda_handler(event, context)
        
        # Should return error response
        assert result['statusCode'] == 500
        body = json.loads(result['body'])
        assert body['error'] == 'Request processing failed'
        assert 'Step Function execution failed' in body['message']
        assert 'Invalid Medium cookies' in body['message']
    
    @patch('lambdas.trigger.stepfunctions_client')
    @patch.dict(os.environ, {'STATE_MACHINE_ARN': 'arn:aws:states:us-east-1:123456789012:stateMachine:medium-digest'})
    def test_aws_service_unavailable(self, mock_stepfunctions):
        """Test handling when AWS Step Functions service is unavailable."""
        # Setup Step Functions mock to simulate service unavailable
        error_response = {
            'Error': {
                'Code': 'ServiceUnavailable',
                'Message': 'The service is temporarily unavailable'
            }
        }
        mock_stepfunctions.start_sync_execution.side_effect = ClientError(error_response, 'StartSyncExecution')
        
        # Test event
        event = {
            'body': json.dumps({
                'payload': '<html><body><a href="https://medium.com/test">Test</a></body></html>'
            })
        }
        context = Mock()
        
        # Execute
        result = lambda_handler(event, context)
        
        # Should return error response
        assert result['statusCode'] == 500
        body = json.loads(result['body'])
        assert body['error'] == 'Request processing failed'
        assert 'AWS Step Functions error (ServiceUnavailable)' in body['message']
    
    @patch('lambdas.trigger.stepfunctions_client')
    @patch.dict(os.environ, {'STATE_MACHINE_ARN': 'arn:aws:states:us-east-1:123456789012:stateMachine:medium-digest'})
    def test_large_payload_handling(self, mock_stepfunctions):
        """Test handling of large email payloads."""
        # Setup Step Functions mock
        mock_stepfunctions.start_sync_execution.return_value = {
            'executionArn': 'arn:aws:states:us-east-1:123456789012:execution:medium-digest:large-123',
            'status': 'SUCCEEDED',
            'output': json.dumps([])  # No articles found
        }
        
        # Create a large email payload (simulate a digest with many articles)
        large_email_content = '<html><body>'
        for i in range(50):  # 50 articles
            large_email_content += f'''
            <div class="article">
                <h2><a href="https://medium.com/@author{i}/article-{i}">Article {i}</a></h2>
                <p>{'Lorem ipsum dolor sit amet, consectetur adipiscing elit. ' * 20}</p>
            </div>
            '''
        large_email_content += '</body></html>'
        
        # Test event
        event = {
            'body': json.dumps({
                'payload': large_email_content
            })
        }
        context = Mock()
        
        # Execute
        result = lambda_handler(event, context)
        
        # Should handle large payload successfully
        assert result['statusCode'] == 200
        body = json.loads(result['body'])
        assert body['message'] == 'Processing completed successfully'
        
        # Verify Step Functions was called with the large payload
        mock_stepfunctions.start_sync_execution.assert_called_once()
        call_args = mock_stepfunctions.start_sync_execution.call_args
        input_data = json.loads(call_args[1]['input'])
        assert len(input_data['payload']) > 10000  # Verify it's actually large
    
    @patch('lambdas.trigger.boto3.client')
    @patch.dict(os.environ, {}, clear=True)
    def test_missing_environment_variables(self, mock_boto3_client):
        """Test handling when required environment variables are missing."""
        # Test event
        event = {
            'body': json.dumps({
                'payload': '<html><body><a href="https://medium.com/test">Test</a></body></html>'
            })
        }
        context = Mock()
        
        # Execute
        result = lambda_handler(event, context)
        
        # Should return error response
        assert result['statusCode'] == 500
        body = json.loads(result['body'])
        assert body['error'] == 'Request processing failed'
        assert 'STATE_MACHINE_ARN environment variable not set' in body['message']
    
    @patch('lambdas.trigger.boto3.client')
    def test_malformed_api_gateway_event(self, mock_boto3_client):
        """Test handling of malformed API Gateway events."""
        # Test with completely malformed event
        event = {
            'Records': [  # This looks like an S3 event, not API Gateway
                {
                    'eventSource': 'aws:s3',
                    's3': {
                        'bucket': {'name': 'test-bucket'},
                        'object': {'key': 'test-key'}
                    }
                }
            ]
        }
        context = Mock()
        
        # Execute
        result = lambda_handler(event, context)
        
        # Should return validation error
        assert result['statusCode'] == 400
        body = json.loads(result['body'])
        assert body['error'] == 'Request processing failed'
        assert 'No body or payload found' in body['message']
    
    @patch('lambdas.trigger.stepfunctions_client')
    @patch.dict(os.environ, {'STATE_MACHINE_ARN': 'arn:aws:states:us-east-1:123456789012:stateMachine:medium-digest'})
    def test_empty_step_function_output(self, mock_stepfunctions):
        """Test handling when Step Function returns empty output."""
        # Setup Step Functions mock with empty output
        mock_stepfunctions.start_sync_execution.return_value = {
            'executionArn': 'arn:aws:states:us-east-1:123456789012:execution:medium-digest:empty-123',
            'status': 'SUCCEEDED',
            'output': json.dumps([])  # Empty array
        }
        
        # Test event
        event = {
            'body': json.dumps({
                'payload': '<html><body>No Medium links here</body></html>'
            })
        }
        context = Mock()
        
        # Execute
        result = lambda_handler(event, context)
        
        # Should return success with 0 articles processed
        assert result['statusCode'] == 200
        body = json.loads(result['body'])
        assert body['message'] == 'Processing completed successfully'
        assert body['articlesProcessed'] == 0
        assert body['status'] == 'SUCCEEDED'
    
    @patch('lambdas.trigger.stepfunctions_client')
    @patch.dict(os.environ, {'STATE_MACHINE_ARN': 'arn:aws:states:us-east-1:123456789012:stateMachine:medium-digest'})
    def test_cors_headers_present(self, mock_stepfunctions):
        """Test that CORS headers are properly set in responses."""
        # Setup Step Functions mock
        mock_stepfunctions.start_sync_execution.return_value = {
            'executionArn': 'arn:aws:states:us-east-1:123456789012:execution:medium-digest:cors-123',
            'status': 'SUCCEEDED',
            'output': json.dumps([])
        }
        
        # Test event
        event = {
            'body': json.dumps({
                'payload': '<html><body><a href="https://medium.com/test">Test</a></body></html>'
            })
        }
        context = Mock()
        
        # Execute
        result = lambda_handler(event, context)
        
        # Verify CORS headers are present
        headers = result['headers']
        assert headers['Access-Control-Allow-Origin'] == '*'
        assert 'Content-Type' in headers['Access-Control-Allow-Headers']
        assert 'Authorization' in headers['Access-Control-Allow-Headers']
        assert 'X-Api-Key' in headers['Access-Control-Allow-Headers']
        assert 'POST' in headers['Access-Control-Allow-Methods']
        assert 'OPTIONS' in headers['Access-Control-Allow-Methods']
    
    @patch('lambdas.trigger.boto3.client')
    def test_validation_error_cors_headers(self, mock_boto3_client):
        """Test that CORS headers are present even in validation error responses."""
        # Test event with validation error
        event = {
            'body': json.dumps({
                'data': 'missing payload key'
            })
        }
        context = Mock()
        
        # Execute
        result = lambda_handler(event, context)
        
        # Verify error response has CORS headers
        assert result['statusCode'] == 400
        headers = result['headers']
        assert headers['Access-Control-Allow-Origin'] == '*'
        assert 'Access-Control-Allow-Headers' in headers
        assert 'Access-Control-Allow-Methods' in headers
    
    @patch('lambdas.trigger.stepfunctions_client')
    @patch.dict(os.environ, {'STATE_MACHINE_ARN': 'arn:aws:states:us-east-1:123456789012:stateMachine:medium-digest'})
    def test_execution_time_tracking(self, mock_stepfunctions):
        """Test that execution time is properly tracked and returned."""
        # Setup Step Functions mock with delay
        def delayed_execution(*args, **kwargs):
            import time
            time.sleep(0.1)  # Simulate some processing time
            return {
                'executionArn': 'arn:aws:states:us-east-1:123456789012:execution:medium-digest:timing-123',
                'status': 'SUCCEEDED',
                'output': json.dumps([])
            }
        
        mock_stepfunctions.start_sync_execution.side_effect = delayed_execution
        
        # Test event
        event = {
            'body': json.dumps({
                'payload': '<html><body><a href="https://medium.com/test">Test</a></body></html>'
            })
        }
        context = Mock()
        
        # Execute
        result = lambda_handler(event, context)
        
        # Verify execution time is tracked
        assert result['statusCode'] == 200
        body = json.loads(result['body'])
        assert 'executionTime' in body
        assert isinstance(body['executionTime'], (int, float))
        assert body['executionTime'] >= 0.1  # Should be at least the sleep time
        assert body['executionTime'] < 1.0   # But not too long for a test