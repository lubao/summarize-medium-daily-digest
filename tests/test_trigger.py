"""
Unit tests for the Trigger Lambda function.
"""
import json
import os
import pytest
from unittest.mock import Mock, patch, MagicMock
from botocore.exceptions import ClientError

# Import the module under test
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from lambdas.trigger import (
    lambda_handler,
    parse_s3_event,
    retrieve_email_content,
    get_state_machine_arn,
    format_step_function_input,
    execute_step_function,
    create_success_response,
    create_error_response
)
from shared.error_handling import ValidationError, FatalError


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
class TestLambdaHandler:
    """Test cases for the main lambda_handler function."""
    
    @patch('lambdas.trigger.boto3.client')
    @patch('lambdas.trigger.execute_step_function')
    @patch('lambdas.trigger.get_state_machine_arn')
    def test_lambda_handler_success(self, mock_get_arn, mock_execute, mock_boto3_client, mock_logger):
        """Test successful lambda handler execution with S3 event."""
        # Setup logger mock
        mock_logger_instance = Mock()
        mock_logger.return_value = mock_logger_instance
        
        # Setup mocks
        mock_get_arn.return_value = 'arn:aws:states:us-east-1:123456789012:stateMachine:test'
        mock_execute.return_value = {
            'executionArn': 'arn:aws:states:us-east-1:123456789012:execution:test:123',
            'status': 'SUCCEEDED'
        }
        
        # Mock S3 client
        mock_s3_client = Mock()
        mock_s3_client.get_object.return_value = {
            'Body': Mock(read=Mock(return_value=b'Test email content with Medium links'))
        }
        mock_boto3_client.return_value = mock_s3_client
        
        # Test S3 event
        event = {
            'Records': [
                {
                    'eventSource': 'aws:s3',
                    's3': {
                        'bucket': {'name': 'test-bucket'},
                        'object': {'key': 'test-email.html'}
                    }
                }
            ]
        }
        context = create_mock_context()
        
        # Execute
        result = lambda_handler(event, context)
        
        # Verify
        assert result['statusCode'] == 200
        body = result['body']
        assert body['message'] == 'S3 event processing completed successfully'
        assert body['processedRecords'] == 1
        assert 'executionTime' in body
        assert len(body['results']) == 1
        assert body['results'][0]['bucket'] == 'test-bucket'
        assert body['results'][0]['key'] == 'test-email.html'
        
        # Verify mocks were called
        mock_get_arn.assert_called_once()
        mock_execute.assert_called_once()
        mock_s3_client.get_object.assert_called_once_with(Bucket='test-bucket', Key='test-email.html')
    
    @patch('lambdas.trigger.boto3.client')
    def test_lambda_handler_validation_error(self, mock_boto3_client, mock_logger):
        """Test lambda handler with S3 event validation error."""
        # Setup logger mock
        mock_logger_instance = Mock()
        mock_logger.return_value = mock_logger_instance
        
        # Test event with missing Records
        event = {
            'eventSource': 'aws:s3'
        }
        context = create_mock_context()
        
        # Execute
        result = lambda_handler(event, context)
        
        # Verify
        assert result['statusCode'] == 400
        body = result['body']
        assert body['error'] == 'S3 event processing failed'
        assert 'Records' in body['message']
    
    @patch('lambdas.trigger.boto3.client')
    @patch('lambdas.trigger.execute_step_function')
    @patch('lambdas.trigger.get_state_machine_arn')
    def test_lambda_handler_step_function_error(self, mock_get_arn, mock_execute, mock_boto3_client):
        """Test lambda handler with Step Function execution error."""
        mock_get_arn.return_value = 'arn:aws:states:us-east-1:123456789012:stateMachine:test'
        mock_execute.side_effect = FatalError("Step Function execution failed")
        
        # Mock S3 client
        mock_s3_client = Mock()
        mock_s3_client.get_object.return_value = {
            'Body': Mock(read=Mock(return_value=b'Test email content'))
        }
        mock_boto3_client.return_value = mock_s3_client
        
        # Test S3 event
        event = {
            'Records': [
                {
                    'eventSource': 'aws:s3',
                    's3': {
                        'bucket': {'name': 'test-bucket'},
                        'object': {'key': 'test-email.html'}
                    }
                }
            ]
        }
        context = Mock()
        
        # Execute
        result = lambda_handler(event, context)
        
        # Verify
        assert result['statusCode'] == 500
        body = result['body']
        assert body['error'] == 'S3 event processing failed'
        assert 'Step Function execution failed' in body['message']
    
    @patch('lambdas.trigger.boto3.client')
    def test_lambda_handler_s3_retrieval_error(self, mock_boto3_client):
        """Test lambda handler with S3 retrieval error."""
        # Mock S3 client to raise error
        mock_s3_client = Mock()
        error_response = {
            'Error': {
                'Code': 'NoSuchKey',
                'Message': 'The specified key does not exist'
            }
        }
        mock_s3_client.get_object.side_effect = ClientError(error_response, 'GetObject')
        mock_boto3_client.return_value = mock_s3_client
        
        # Test S3 event
        event = {
            'Records': [
                {
                    'eventSource': 'aws:s3',
                    's3': {
                        'bucket': {'name': 'test-bucket'},
                        'object': {'key': 'nonexistent-email.html'}
                    }
                }
            ]
        }
        context = Mock()
        
        # Execute
        result = lambda_handler(event, context)
        
        # Verify
        assert result['statusCode'] == 500
        body = result['body']
        assert body['error'] == 'S3 event processing failed'
        assert 'S3 object not found' in body['message']
    
    @patch('lambdas.trigger.boto3.client')
    def test_lambda_handler_unexpected_error(self, mock_boto3_client):
        """Test lambda handler with unexpected error."""
        # Test event that will cause a validation error (None event)
        event = None  # This will cause an error when accessing event keys
        context = Mock()
        
        # Execute
        result = lambda_handler(event, context)
        
        # Verify - this actually causes a validation error, not an unexpected error
        assert result['statusCode'] == 400
        body = result['body']
        assert body['error'] == 'S3 event processing failed'
        assert 'Failed to parse S3 event' in body['message']


class TestParseS3Event:
    """Test cases for S3 event parsing."""
    
    def test_parse_valid_s3_event(self):
        """Test parsing a valid S3 event."""
        event = {
            'Records': [
                {
                    'eventSource': 'aws:s3',
                    's3': {
                        'bucket': {'name': 'test-bucket'},
                        'object': {'key': 'test-email.html'}
                    }
                }
            ]
        }
        
        result = parse_s3_event(event, Mock())
        assert len(result) == 1
        assert result[0]['bucket'] == 'test-bucket'
        assert result[0]['key'] == 'test-email.html'
    
    def test_parse_multiple_s3_records(self):
        """Test parsing S3 event with multiple records."""
        event = {
            'Records': [
                {
                    'eventSource': 'aws:s3',
                    's3': {
                        'bucket': {'name': 'test-bucket'},
                        'object': {'key': 'email1.html'}
                    }
                },
                {
                    'eventSource': 'aws:s3',
                    's3': {
                        'bucket': {'name': 'test-bucket'},
                        'object': {'key': 'email2.html'}
                    }
                }
            ]
        }
        
        result = parse_s3_event(event, Mock())
        assert len(result) == 2
        assert result[0]['key'] == 'email1.html'
        assert result[1]['key'] == 'email2.html'
    
    def test_parse_url_encoded_object_key(self):
        """Test parsing S3 event with URL-encoded object key."""
        event = {
            'Records': [
                {
                    'eventSource': 'aws:s3',
                    's3': {
                        'bucket': {'name': 'test-bucket'},
                        'object': {'key': 'folder%2Ftest%20email.html'}
                    }
                }
            ]
        }
        
        result = parse_s3_event(event, Mock())
        assert result[0]['key'] == 'folder/test email.html'
    
    def test_parse_missing_records(self):
        """Test parsing S3 event with missing Records key."""
        event = {
            'eventSource': 'aws:s3'
        }
        
        with pytest.raises(ValidationError) as exc_info:
            parse_s3_event(event, Mock())
        
        assert 'missing \'Records\' key' in str(exc_info.value)
    
    def test_parse_empty_records(self):
        """Test parsing S3 event with empty Records list."""
        event = {
            'Records': []
        }
        
        with pytest.raises(ValidationError) as exc_info:
            parse_s3_event(event, Mock())
        
        assert 'empty \'Records\' list' in str(exc_info.value)
    
    def test_parse_non_s3_event_source(self):
        """Test parsing event with non-S3 event source."""
        event = {
            'Records': [
                {
                    'eventSource': 'aws:sns',
                    's3': {
                        'bucket': {'name': 'test-bucket'},
                        'object': {'key': 'test-email.html'}
                    }
                }
            ]
        }
        
        with pytest.raises(ValidationError) as exc_info:
            parse_s3_event(event, Mock())
        
        assert 'eventSource must be \'aws:s3\'' in str(exc_info.value)
    
    def test_parse_missing_s3_key(self):
        """Test parsing S3 record with missing s3 key."""
        event = {
            'Records': [
                {
                    'eventSource': 'aws:s3',
                    'eventName': 's3:ObjectCreated:Put'
                }
            ]
        }
        
        with pytest.raises(ValidationError) as exc_info:
            parse_s3_event(event, Mock())
        
        assert 'missing \'s3\' key' in str(exc_info.value)
    
    def test_parse_missing_bucket_info(self):
        """Test parsing S3 record with missing bucket information."""
        event = {
            'Records': [
                {
                    'eventSource': 'aws:s3',
                    's3': {
                        'object': {'key': 'test-email.html'}
                    }
                }
            ]
        }
        
        with pytest.raises(ValidationError) as exc_info:
            parse_s3_event(event, Mock())
        
        assert 'missing bucket information' in str(exc_info.value)
    
    def test_parse_missing_object_info(self):
        """Test parsing S3 record with missing object information."""
        event = {
            'Records': [
                {
                    'eventSource': 'aws:s3',
                    's3': {
                        'bucket': {'name': 'test-bucket'}
                    }
                }
            ]
        }
        
        with pytest.raises(ValidationError) as exc_info:
            parse_s3_event(event, Mock())
        
        assert 'missing object information' in str(exc_info.value)
    
    def test_parse_invalid_bucket_name(self):
        """Test parsing S3 record with invalid bucket name."""
        event = {
            'Records': [
                {
                    'eventSource': 'aws:s3',
                    's3': {
                        'bucket': {'name': ''},
                        'object': {'key': 'test-email.html'}
                    }
                }
            ]
        }
        
        with pytest.raises(ValidationError) as exc_info:
            parse_s3_event(event, Mock())
        
        assert 'invalid bucket name' in str(exc_info.value)
    
    def test_parse_invalid_object_key(self):
        """Test parsing S3 record with invalid object key."""
        event = {
            'Records': [
                {
                    'eventSource': 'aws:s3',
                    's3': {
                        'bucket': {'name': 'test-bucket'},
                        'object': {'key': ''}
                    }
                }
            ]
        }
        
        with pytest.raises(ValidationError) as exc_info:
            parse_s3_event(event, Mock())
        
        assert 'invalid object key' in str(exc_info.value)


class TestRetrieveEmailContent:
    """Test cases for retrieving email content from S3."""
    
    @patch('lambdas.trigger.s3_client')
    def test_retrieve_email_content_success(self, mock_s3_client):
        """Test successful email content retrieval."""
        # Setup mock
        mock_s3_client.get_object.return_value = {
            'Body': Mock(read=Mock(return_value=b'Test email content'))
        }
        
        # Execute
        result = retrieve_email_content('test-bucket', 'test-email.html', Mock())
        
        # Verify
        assert result == 'Test email content'
        mock_s3_client.get_object.assert_called_once_with(Bucket='test-bucket', Key='test-email.html')
    
    @patch('lambdas.trigger.s3_client')
    def test_retrieve_email_content_utf8_decoding(self, mock_s3_client):
        """Test email content retrieval with UTF-8 decoding."""
        # Setup mock with UTF-8 content
        utf8_content = 'Test email with unicode: café'
        mock_s3_client.get_object.return_value = {
            'Body': Mock(read=Mock(return_value=utf8_content.encode('utf-8')))
        }
        
        # Execute
        result = retrieve_email_content('test-bucket', 'test-email.html', Mock())
        
        # Verify
        assert result == utf8_content
    
    @patch('lambdas.trigger.s3_client')
    def test_retrieve_email_content_latin1_fallback(self, mock_s3_client):
        """Test email content retrieval with latin-1 fallback."""
        # Setup mock with content that fails UTF-8 but works with latin-1
        latin1_content = b'\xe9\xe8\xe7'  # Some latin-1 bytes that aren't valid UTF-8
        mock_s3_client.get_object.return_value = {
            'Body': Mock(read=Mock(return_value=latin1_content))
        }
        
        # Execute
        result = retrieve_email_content('test-bucket', 'test-email.html', Mock())
        
        # Verify - should decode with latin-1
        assert result == latin1_content.decode('latin-1')
    
    @patch('lambdas.trigger.s3_client')
    def test_retrieve_email_content_empty_content(self, mock_s3_client):
        """Test email content retrieval with empty content."""
        # Setup mock with empty content
        mock_s3_client.get_object.return_value = {
            'Body': Mock(read=Mock(return_value=b''))
        }
        
        # Execute and verify exception
        with pytest.raises(FatalError) as exc_info:
            retrieve_email_content('test-bucket', 'test-email.html', Mock())
        
        assert 'Email content is empty' in str(exc_info.value)
    
    @patch('lambdas.trigger.s3_client')
    def test_retrieve_email_content_no_such_key(self, mock_s3_client):
        """Test email content retrieval with NoSuchKey error."""
        # Setup mock to raise NoSuchKey error
        error_response = {
            'Error': {
                'Code': 'NoSuchKey',
                'Message': 'The specified key does not exist'
            }
        }
        mock_s3_client.get_object.side_effect = ClientError(error_response, 'GetObject')
        
        # Execute and verify exception
        with pytest.raises(FatalError) as exc_info:
            retrieve_email_content('test-bucket', 'nonexistent.html', Mock())
        
        assert 'S3 object not found' in str(exc_info.value)
    
    @patch('lambdas.trigger.s3_client')
    def test_retrieve_email_content_no_such_bucket(self, mock_s3_client):
        """Test email content retrieval with NoSuchBucket error."""
        # Setup mock to raise NoSuchBucket error
        error_response = {
            'Error': {
                'Code': 'NoSuchBucket',
                'Message': 'The specified bucket does not exist'
            }
        }
        mock_s3_client.get_object.side_effect = ClientError(error_response, 'GetObject')
        
        # Execute and verify exception
        with pytest.raises(FatalError) as exc_info:
            retrieve_email_content('nonexistent-bucket', 'test.html', Mock())
        
        assert 'S3 bucket not found' in str(exc_info.value)
    
    @patch('lambdas.trigger.s3_client')
    def test_retrieve_email_content_access_denied(self, mock_s3_client):
        """Test email content retrieval with AccessDenied error."""
        # Setup mock to raise AccessDenied error
        error_response = {
            'Error': {
                'Code': 'AccessDenied',
                'Message': 'Access Denied'
            }
        }
        mock_s3_client.get_object.side_effect = ClientError(error_response, 'GetObject')
        
        # Execute and verify exception
        with pytest.raises(FatalError) as exc_info:
            retrieve_email_content('test-bucket', 'test.html', Mock())
        
        assert 'Access denied to S3 object' in str(exc_info.value)


class TestGetStateMachineArn:
    """Test cases for getting state machine ARN."""
    
    @patch.dict(os.environ, {'STATE_MACHINE_ARN': 'arn:aws:states:us-east-1:123456789012:stateMachine:test'})
    def test_get_state_machine_arn_success(self):
        """Test successful retrieval of state machine ARN."""
        result = get_state_machine_arn(Mock())
        assert result == 'arn:aws:states:us-east-1:123456789012:stateMachine:test'
    
    @patch.dict(os.environ, {}, clear=True)
    def test_get_state_machine_arn_missing(self):
        """Test error when state machine ARN is not set."""
        with pytest.raises(FatalError) as exc_info:
            get_state_machine_arn(Mock())
        
        assert 'STATE_MACHINE_ARN environment variable not set' in str(exc_info.value)


class TestFormatStepFunctionInput:
    """Test cases for formatting Step Function input."""
    
    @patch('time.time', return_value=1234567890)
    def test_format_step_function_input(self, mock_time):
        """Test formatting of Step Function input."""
        email_content = 'Test email content'
        bucket_name = 'test-bucket'
        object_key = 'test-email.html'
        
        result = format_step_function_input(email_content, bucket_name, object_key)
        
        expected = {
            'payload': 'Test email content',
            'timestamp': 1234567890,
            'source': 's3_event',
            's3': {
                'bucket': 'test-bucket',
                'key': 'test-email.html'
            }
        }
        
        assert result == expected


class TestExecuteStepFunction:
    """Test cases for Step Function execution."""
    
    @patch('lambdas.trigger.stepfunctions_client')
    @patch('time.time', return_value=1234567890)
    @patch('os.urandom', return_value=b'abcd')
    def test_execute_step_function_success(self, mock_urandom, mock_time, mock_client):
        """Test successful Step Function execution."""
        # Setup mock
        mock_client.start_sync_execution.return_value = {
            'executionArn': 'arn:aws:states:us-east-1:123456789012:execution:test:123',
            'status': 'SUCCEEDED',
            'output': json.dumps({'result': 'success'})
        }
        
        # Test data
        state_machine_arn = 'arn:aws:states:us-east-1:123456789012:stateMachine:test'
        input_data = {'payload': 'test'}
        
        # Execute
        result = execute_step_function(state_machine_arn, input_data, Mock())
        
        # Verify
        assert result['status'] == 'SUCCEEDED'
        assert 'executionArn' in result
        
        # Verify client was called correctly
        mock_client.start_sync_execution.assert_called_once_with(
            stateMachineArn=state_machine_arn,
            name='medium-digest-1234567890-61626364',
            input=json.dumps(input_data)
        )
    
    @patch('lambdas.trigger.stepfunctions_client')
    def test_execute_step_function_failed_status(self, mock_client):
        """Test Step Function execution with failed status."""
        # Setup mock
        mock_client.start_sync_execution.return_value = {
            'executionArn': 'arn:aws:states:us-east-1:123456789012:execution:test:123',
            'status': 'FAILED',
            'error': 'ValidationError',
            'cause': 'Invalid input format'
        }
        
        # Test data
        state_machine_arn = 'arn:aws:states:us-east-1:123456789012:stateMachine:test'
        input_data = {'payload': 'test'}
        
        # Execute and verify exception
        with pytest.raises(FatalError) as exc_info:
            execute_step_function(state_machine_arn, input_data, Mock())
        
        assert 'Step Function execution failed: ValidationError' in str(exc_info.value)
        assert 'Invalid input format' in str(exc_info.value)
    
    @patch('lambdas.trigger.stepfunctions_client')
    def test_execute_step_function_client_error(self, mock_client):
        """Test Step Function execution with AWS client error."""
        # Setup mock
        error_response = {
            'Error': {
                'Code': 'StateMachineDoesNotExist',
                'Message': 'State Machine does not exist'
            }
        }
        mock_client.start_sync_execution.side_effect = ClientError(error_response, 'StartSyncExecution')
        
        # Test data
        state_machine_arn = 'arn:aws:states:us-east-1:123456789012:stateMachine:nonexistent'
        input_data = {'payload': 'test'}
        
        # Execute and verify exception
        with pytest.raises(FatalError) as exc_info:
            execute_step_function(state_machine_arn, input_data, Mock())
        
        assert 'AWS Step Functions error (StateMachineDoesNotExist)' in str(exc_info.value)
        assert 'State Machine does not exist' in str(exc_info.value)
    
    @patch('lambdas.trigger.stepfunctions_client')
    def test_execute_step_function_unexpected_error(self, mock_client):
        """Test Step Function execution with unexpected error."""
        # Setup mock
        mock_client.start_sync_execution.side_effect = Exception('Unexpected error')
        
        # Test data
        state_machine_arn = 'arn:aws:states:us-east-1:123456789012:stateMachine:test'
        input_data = {'payload': 'test'}
        
        # Execute and verify exception
        with pytest.raises(FatalError) as exc_info:
            execute_step_function(state_machine_arn, input_data, Mock())
        
        assert 'Failed to execute Step Function: Unexpected error' in str(exc_info.value)


class TestCreateSuccessResponse:
    """Test cases for creating success responses."""
    
    def test_create_success_response_single_record(self):
        """Test creating success response for single S3 record."""
        results = [
            {
                'bucket': 'test-bucket',
                'key': 'test-email.html',
                'executionArn': 'arn:aws:states:us-east-1:123456789012:execution:test:123',
                'status': 'SUCCEEDED'
            }
        ]
        execution_time = 5.67
        
        result = create_success_response(results, execution_time)
        
        assert result['statusCode'] == 200
        
        body = result['body']
        assert body['message'] == 'S3 event processing completed successfully'
        assert body['processedRecords'] == 1
        assert body['executionTime'] == 5.67
        assert len(body['results']) == 1
        assert body['results'][0]['bucket'] == 'test-bucket'
        assert body['results'][0]['key'] == 'test-email.html'
    
    def test_create_success_response_multiple_records(self):
        """Test creating success response for multiple S3 records."""
        results = [
            {
                'bucket': 'test-bucket',
                'key': 'email1.html',
                'executionArn': 'arn:aws:states:us-east-1:123456789012:execution:test:123',
                'status': 'SUCCEEDED'
            },
            {
                'bucket': 'test-bucket',
                'key': 'email2.html',
                'executionArn': 'arn:aws:states:us-east-1:123456789012:execution:test:456',
                'status': 'SUCCEEDED'
            }
        ]
        execution_time = 3.14
        
        result = create_success_response(results, execution_time)
        
        body = result['body']
        assert body['processedRecords'] == 2
        assert len(body['results']) == 2
    
    def test_create_success_response_empty_results(self):
        """Test creating success response with empty results."""
        results = []
        execution_time = 1.0
        
        result = create_success_response(results, execution_time)
        
        body = result['body']
        assert body['processedRecords'] == 0
        assert body['results'] == []


class TestCreateErrorResponse:
    """Test cases for creating error responses."""
    
    def test_create_error_response_400(self):
        """Test creating 400 error response."""
        error_message = 'Invalid S3 event format'
        status_code = 400
        execution_time = 0.5
        
        result = create_error_response(error_message, status_code, execution_time, Mock())
        
        assert result['statusCode'] == 400
        
        body = result['body']
        assert body['error'] == 'S3 event processing failed'
        assert body['message'] == 'Invalid S3 event format'
        assert body['executionTime'] == 0.5
    
    def test_create_error_response_500(self):
        """Test creating 500 error response."""
        error_message = 'S3 retrieval failed'
        status_code = 500
        execution_time = 2.3
        
        result = create_error_response(error_message, status_code, execution_time, Mock())
        
        assert result['statusCode'] == 500
        
        body = result['body']
        assert body['error'] == 'S3 event processing failed'
        assert body['message'] == 'S3 retrieval failed'
        assert body['executionTime'] == 2.3


class TestIntegrationScenarios:
    """Integration test scenarios for the Trigger Lambda."""
    
    @patch('lambdas.trigger.execute_step_function')
    @patch('lambdas.trigger.get_state_machine_arn')
    @patch('lambdas.trigger.boto3.client')
    def test_complete_s3_event_flow(self, mock_boto3_client, mock_get_arn, mock_execute):
        """Test complete flow from S3 event to Step Function execution."""
        # Setup mocks
        mock_get_arn.return_value = 'arn:aws:states:us-east-1:123456789012:stateMachine:test'
        execution_result = {
            'executionArn': 'arn:aws:states:us-east-1:123456789012:execution:test:123',
            'status': 'SUCCEEDED'
        }
        mock_execute.return_value = execution_result
        
        # Mock S3 client
        mock_s3_client = Mock()
        email_content = '''
        <html>
            <body>
                <h1>Medium Daily Digest</h1>
                <a href="https://medium.com/test-article">Test Article</a>
            </body>
        </html>
        '''
        mock_s3_client.get_object.return_value = {
            'Body': Mock(read=Mock(return_value=email_content.encode('utf-8')))
        }
        mock_boto3_client.return_value = mock_s3_client
        
        # Simulate S3 event
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
        context = Mock()
        context.aws_request_id = 'lambda-request-456'
        context.function_name = 'medium-digest-trigger'
        
        # Execute
        result = lambda_handler(event, context)
        
        # Verify response structure
        assert result['statusCode'] == 200
        
        body = result['body']
        assert body['message'] == 'S3 event processing completed successfully'
        assert body['processedRecords'] == 1
        assert 'executionTime' in body
        assert len(body['results']) == 1
        assert body['results'][0]['bucket'] == 'medium-digest-emails'
        assert body['results'][0]['key'] == 'daily-digest-2024-01-15.html'
        assert body['results'][0]['status'] == 'SUCCEEDED'
        
        # Verify S3 was called correctly
        mock_s3_client.get_object.assert_called_once_with(
            Bucket='medium-digest-emails', 
            Key='daily-digest-2024-01-15.html'
        )
        
        # Verify Step Function was called
        mock_execute.assert_called_once()
        call_args = mock_execute.call_args
        
        # Verify the input contains the email content and S3 metadata
        input_data = call_args[0][1]  # Second argument to execute_step_function
        assert 'payload' in input_data
        assert 'timestamp' in input_data
        assert input_data['source'] == 's3_event'
        assert 's3' in input_data
        assert input_data['s3']['bucket'] == 'medium-digest-emails'
        assert input_data['s3']['key'] == 'daily-digest-2024-01-15.html'
        assert input_data['payload'] == email_content