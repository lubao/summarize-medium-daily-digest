"""
Trigger Lambda function for S3 event integration and Step Function execution.
"""
import json
import time
from typing import Dict, Any, Optional, List

import boto3
from botocore.exceptions import ClientError

# Import shared utilities
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from shared.error_handling import ValidationError, FatalError, handle_fatal_error
from shared.models import ProcessingResult
from shared.logging_utils import (
    create_lambda_logger, StructuredLogger, ErrorCategory, PerformanceTracker
)

# Initialize AWS clients (will be initialized in lambda_handler to handle region)
stepfunctions_client = None
s3_client = None


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler for S3 event integration and Step Function execution.
    
    Args:
        event: S3 event containing bucket and object information
        context: Lambda context object
        
    Returns:
        Processing result with success/error status
    """
    global stepfunctions_client, s3_client
    
    # Initialize structured logger and performance tracker
    logger = create_lambda_logger("trigger", event, context)
    tracker = PerformanceTracker()
    
    # Initialize AWS clients if not already done
    if stepfunctions_client is None:
        stepfunctions_client = boto3.client('stepfunctions')
    if s3_client is None:
        s3_client = boto3.client('s3')
    
    try:
        logger.log_execution_start("trigger_lambda", event_type=type(event).__name__)
        
        # Parse S3 event to extract bucket and object information
        tracker.checkpoint("s3_event_parsing_start")
        s3_records = parse_s3_event(event, logger)
        tracker.checkpoint("s3_event_parsing_complete")
        tracker.record_metric("s3_records_count", len(s3_records))
        
        logger.info("Successfully parsed S3 event", 
                   records_count=len(s3_records))
        
        # Process each S3 record (usually just one for email uploads)
        results = []
        for record in s3_records:
            bucket_name = record['bucket']
            object_key = record['key']
            
            logger.info("Processing S3 object", 
                       bucket=bucket_name, 
                       key=object_key)
            
            # Retrieve email content from S3
            tracker.checkpoint("s3_retrieval_start")
            email_content = retrieve_email_content(bucket_name, object_key, logger)
            tracker.checkpoint("s3_retrieval_complete")
            tracker.record_metric("email_content_size_chars", len(email_content))
            
            logger.info("Successfully retrieved email content from S3", 
                       content_size=len(email_content),
                       bucket=bucket_name,
                       key=object_key)
            
            # Get Step Function ARN from environment variable
            state_machine_arn = get_state_machine_arn(logger)
            logger.info("Retrieved Step Function ARN", state_machine_arn=state_machine_arn)
            
            # Format input for Step Function execution
            tracker.checkpoint("format_input_start")
            step_function_input = format_step_function_input(email_content, bucket_name, object_key)
            tracker.checkpoint("format_input_complete")
            
            logger.info("Formatted Step Function input")
            
            # Execute Step Function
            tracker.checkpoint("step_function_start")
            execution_result = execute_step_function(state_machine_arn, step_function_input, logger)
            tracker.checkpoint("step_function_complete")
            
            logger.info("Step Function execution started", 
                       execution_arn=execution_result['executionArn'],
                       status=execution_result['status'],
                       bucket=bucket_name,
                       key=object_key)
            
            results.append({
                'bucket': bucket_name,
                'key': object_key,
                'executionArn': execution_result['executionArn'],
                'status': execution_result['status']
            })
        
        # Create success response
        response = create_success_response(results, tracker.get_elapsed_time())
        
        # Log success metrics
        metrics = tracker.get_metrics()
        metrics.update({
            "processed_records": len(results),
            "total_execution_arns": [r['executionArn'] for r in results]
        })
        
        logger.log_execution_end("trigger_lambda", success=True, metrics=metrics)
        
        return response
        
    except ValidationError as e:
        logger.error("Validation error occurred", error=e, category=ErrorCategory.INPUT_VALIDATION)
        return create_error_response(str(e), 400, tracker.get_elapsed_time(), logger)
    
    except FatalError as e:
        logger.error("Fatal error occurred", error=e, category=ErrorCategory.PROCESSING)
        return create_error_response(str(e), 500, tracker.get_elapsed_time(), logger)
    
    except Exception as e:
        logger.critical("Unexpected error in trigger lambda", error=e, 
                       category=ErrorCategory.UNKNOWN, 
                       metrics=tracker.get_metrics(),
                       s3_records_count=len(s3_records) if 's3_records' in locals() else 0)
        return create_error_response("Internal server error", 500, tracker.get_elapsed_time(), logger)


def parse_s3_event(event: Dict[str, Any], logger: StructuredLogger) -> List[Dict[str, str]]:
    """
    Parse S3 event to extract bucket and object key information.
    
    Args:
        event: S3 event dictionary
        logger: Structured logger instance
        
    Returns:
        List of dictionaries containing bucket and key information
        
    Raises:
        ValidationError: If event is invalid or missing required fields
    """
    try:
        logger.info("Starting S3 event parsing", event_keys=list(event.keys()))
        
        # Validate event structure
        if not isinstance(event, dict):
            logger.error("Event must be a dictionary", event_type=type(event).__name__)
            raise ValidationError("Event must be a dictionary")
        
        # Check for Records key (standard S3 event structure)
        if 'Records' not in event:
            logger.error("Missing 'Records' key in S3 event", event_structure=list(event.keys()))
            raise ValidationError("Invalid S3 event: missing 'Records' key")
        
        records = event['Records']
        if not isinstance(records, list):
            logger.error("Records must be a list", records_type=type(records).__name__)
            raise ValidationError("Invalid S3 event: 'Records' must be a list")
        
        if not records:
            logger.error("Records list is empty")
            raise ValidationError("Invalid S3 event: empty 'Records' list")
        
        logger.info("Found S3 records", records_count=len(records))
        
        # Parse each record
        parsed_records = []
        for i, record in enumerate(records):
            try:
                logger.info(f"Parsing S3 record {i+1}", record_keys=list(record.keys()) if isinstance(record, dict) else None)
                
                # Validate record structure
                if not isinstance(record, dict):
                    logger.error(f"Record {i+1} must be a dictionary", record_type=type(record).__name__)
                    raise ValidationError(f"Invalid S3 record {i+1}: must be a dictionary")
                
                # Check for eventSource to confirm it's an S3 event
                event_source = record.get('eventSource')
                if event_source != 'aws:s3':
                    logger.error(f"Record {i+1} is not from S3", event_source=event_source)
                    raise ValidationError(f"Invalid S3 record {i+1}: eventSource must be 'aws:s3'")
                
                # Extract S3 information
                if 's3' not in record:
                    logger.error(f"Record {i+1} missing 's3' key", record_keys=list(record.keys()))
                    raise ValidationError(f"Invalid S3 record {i+1}: missing 's3' key")
                
                s3_info = record['s3']
                if not isinstance(s3_info, dict):
                    logger.error(f"Record {i+1} s3 info must be a dictionary", s3_type=type(s3_info).__name__)
                    raise ValidationError(f"Invalid S3 record {i+1}: 's3' must be a dictionary")
                
                # Extract bucket information
                if 'bucket' not in s3_info:
                    logger.error(f"Record {i+1} missing bucket information", s3_keys=list(s3_info.keys()))
                    raise ValidationError(f"Invalid S3 record {i+1}: missing bucket information")
                
                bucket_info = s3_info['bucket']
                if not isinstance(bucket_info, dict) or 'name' not in bucket_info:
                    logger.error(f"Record {i+1} invalid bucket structure", bucket_info=bucket_info)
                    raise ValidationError(f"Invalid S3 record {i+1}: invalid bucket structure")
                
                bucket_name = bucket_info['name']
                if not bucket_name or not isinstance(bucket_name, str):
                    logger.error(f"Record {i+1} invalid bucket name", bucket_name=bucket_name)
                    raise ValidationError(f"Invalid S3 record {i+1}: invalid bucket name")
                
                # Extract object information
                if 'object' not in s3_info:
                    logger.error(f"Record {i+1} missing object information", s3_keys=list(s3_info.keys()))
                    raise ValidationError(f"Invalid S3 record {i+1}: missing object information")
                
                object_info = s3_info['object']
                if not isinstance(object_info, dict) or 'key' not in object_info:
                    logger.error(f"Record {i+1} invalid object structure", object_info=object_info)
                    raise ValidationError(f"Invalid S3 record {i+1}: invalid object structure")
                
                object_key = object_info['key']
                if not object_key or not isinstance(object_key, str):
                    logger.error(f"Record {i+1} invalid object key", object_key=object_key)
                    raise ValidationError(f"Invalid S3 record {i+1}: invalid object key")
                
                # URL decode the object key (S3 keys are URL encoded in events)
                import urllib.parse
                object_key = urllib.parse.unquote_plus(object_key)
                
                parsed_record = {
                    'bucket': bucket_name,
                    'key': object_key
                }
                
                parsed_records.append(parsed_record)
                logger.info(f"Successfully parsed S3 record {i+1}", 
                           bucket=bucket_name, 
                           key=object_key)
                
            except ValidationError:
                raise
            except Exception as e:
                logger.error(f"Unexpected error parsing S3 record {i+1}", error=e, 
                           category=ErrorCategory.PROCESSING)
                raise ValidationError(f"Failed to parse S3 record {i+1}: {str(e)}")
        
        logger.info("Successfully parsed all S3 records", 
                   total_records=len(parsed_records))
        return parsed_records
        
    except ValidationError:
        raise
    except Exception as e:
        logger.error("Unexpected error during S3 event parsing", error=e, 
                    category=ErrorCategory.PROCESSING)
        raise ValidationError(f"Failed to parse S3 event: {str(e)}")


def retrieve_email_content(bucket_name: str, object_key: str, logger: StructuredLogger) -> str:
    """
    Retrieve email content from S3 object.
    
    Args:
        bucket_name: S3 bucket name
        object_key: S3 object key
        logger: Structured logger instance
        
    Returns:
        Email content as string
        
    Raises:
        FatalError: If S3 retrieval fails
    """
    try:
        logger.info("Retrieving email content from S3", 
                   bucket=bucket_name, 
                   key=object_key)
        
        # Get object from S3
        response = s3_client.get_object(Bucket=bucket_name, Key=object_key)
        
        # Read content from response
        content = response['Body'].read()
        
        # Decode content (handle different encodings)
        if isinstance(content, bytes):
            # Try UTF-8 first, then fall back to other encodings
            try:
                email_content = content.decode('utf-8')
                logger.info("Successfully decoded content as UTF-8")
            except UnicodeDecodeError:
                try:
                    email_content = content.decode('latin-1')
                    logger.info("Successfully decoded content as latin-1")
                except UnicodeDecodeError:
                    # Last resort - decode with errors ignored
                    email_content = content.decode('utf-8', errors='ignore')
                    logger.warning("Decoded content with UTF-8 ignoring errors")
        else:
            email_content = str(content)
            logger.info("Content was already a string")
        
        # Validate content is not empty
        if not email_content.strip():
            logger.error("Retrieved email content is empty", 
                        bucket=bucket_name, 
                        key=object_key)
            raise FatalError(f"Email content is empty for S3 object s3://{bucket_name}/{object_key}")
        
        logger.info("Successfully retrieved email content from S3", 
                   content_size=len(email_content),
                   bucket=bucket_name,
                   key=object_key)
        
        return email_content
        
    except ClientError as e:
        error_code = e.response['Error']['Code']
        error_message = e.response['Error']['Message']
        
        if error_code == 'NoSuchKey':
            logger.error("S3 object not found", 
                        bucket=bucket_name, 
                        key=object_key,
                        category=ErrorCategory.INPUT_VALIDATION)
            raise FatalError(f"S3 object not found: s3://{bucket_name}/{object_key}")
        elif error_code == 'NoSuchBucket':
            logger.error("S3 bucket not found", 
                        bucket=bucket_name,
                        category=ErrorCategory.CONFIGURATION)
            raise FatalError(f"S3 bucket not found: {bucket_name}")
        elif error_code == 'AccessDenied':
            logger.error("Access denied to S3 object", 
                        bucket=bucket_name, 
                        key=object_key,
                        category=ErrorCategory.AUTHENTICATION)
            raise FatalError(f"Access denied to S3 object: s3://{bucket_name}/{object_key}")
        else:
            logger.error("AWS S3 client error", 
                        error_code=error_code,
                        error_message=error_message,
                        bucket=bucket_name,
                        key=object_key,
                        category=ErrorCategory.EXTERNAL_SERVICE)
            raise FatalError(f"AWS S3 error ({error_code}): {error_message}")
    
    except Exception as e:
        logger.error("Unexpected error retrieving email content from S3", 
                    error=e, 
                    bucket=bucket_name,
                    key=object_key,
                    category=ErrorCategory.EXTERNAL_SERVICE)
        raise FatalError(f"Failed to retrieve email content from S3: {str(e)}")


def get_state_machine_arn(logger: StructuredLogger) -> str:
    """
    Get Step Function state machine ARN from environment variable.
    
    Args:
        logger: Structured logger instance
    
    Returns:
        State machine ARN string
        
    Raises:
        FatalError: If ARN is not configured
    """
    state_machine_arn = os.environ.get('STATE_MACHINE_ARN')
    
    if not state_machine_arn:
        logger.error("STATE_MACHINE_ARN environment variable not set", 
                    category=ErrorCategory.CONFIGURATION)
        raise FatalError("STATE_MACHINE_ARN environment variable not set")
    
    logger.info("Retrieved Step Function ARN from environment")
    return state_machine_arn


def format_step_function_input(email_content: str, bucket_name: str, object_key: str) -> Dict[str, Any]:
    """
    Format input for Step Function execution.
    
    Args:
        email_content: Email content string
        bucket_name: S3 bucket name
        object_key: S3 object key
        
    Returns:
        Formatted input dictionary for Step Function
    """
    return {
        "payload": email_content,
        "timestamp": int(time.time()),
        "source": "s3_event",
        "s3": {
            "bucket": bucket_name,
            "key": object_key
        }
    }


def execute_step_function(state_machine_arn: str, input_data: Dict[str, Any], 
                         logger: StructuredLogger) -> Dict[str, Any]:
    """
    Execute Step Function with the provided input.
    
    Args:
        state_machine_arn: ARN of the Step Function state machine
        input_data: Input data for the Step Function
        logger: Structured logger instance
        
    Returns:
        Step Function execution result
        
    Raises:
        FatalError: If Step Function execution fails
    """
    try:
        # Generate unique execution name
        execution_name = f"medium-digest-{int(time.time())}-{os.urandom(4).hex()}"
        
        logger.info("Starting Step Function execution", 
                   execution_name=execution_name,
                   input_size=len(json.dumps(input_data)))
        
        # Start Step Function execution
        response = stepfunctions_client.start_sync_execution(
            stateMachineArn=state_machine_arn,
            name=execution_name,
            input=json.dumps(input_data)
        )
        
        logger.info("Step Function execution completed", 
                   status=response['status'],
                   execution_arn=response.get('executionArn'))
        
        # Check execution status
        if response['status'] == 'FAILED':
            error_message = response.get('error', 'Unknown error')
            cause = response.get('cause', 'No cause provided')
            logger.error("Step Function execution failed", 
                        error_message=error_message, 
                        cause=cause,
                        category=ErrorCategory.EXTERNAL_SERVICE)
            raise FatalError(f"Step Function execution failed: {error_message}. Cause: {cause}")
        
        return response
        
    except ClientError as e:
        error_code = e.response['Error']['Code']
        error_message = e.response['Error']['Message']
        logger.error("AWS Step Functions client error", 
                    error_code=error_code,
                    error_message=error_message,
                    category=ErrorCategory.EXTERNAL_SERVICE)
        raise FatalError(f"AWS Step Functions error ({error_code}): {error_message}")
    
    except Exception as e:
        logger.error("Unexpected error executing Step Function", 
                    error=e, category=ErrorCategory.EXTERNAL_SERVICE)
        raise FatalError(f"Failed to execute Step Function: {str(e)}")


def create_success_response(results: List[Dict[str, Any]], execution_time: float) -> Dict[str, Any]:
    """
    Create success response for S3 event processing.
    
    Args:
        results: List of processing results for each S3 record
        execution_time: Total execution time in seconds
        
    Returns:
        Processing success response
    """
    response_body = {
        "message": "S3 event processing completed successfully",
        "processedRecords": len(results),
        "executionTime": round(execution_time, 2),
        "results": results
    }
    
    return {
        "statusCode": 200,
        "body": response_body
    }


def create_error_response(error_message: str, status_code: int, execution_time: float,
                         logger: StructuredLogger) -> Dict[str, Any]:
    """
    Create error response for S3 event processing.
    
    Args:
        error_message: Error message to include in response
        status_code: HTTP status code
        execution_time: Total execution time in seconds
        logger: Structured logger instance
        
    Returns:
        Processing error response
    """
    response_body = {
        "error": "S3 event processing failed",
        "message": error_message,
        "executionTime": round(execution_time, 2)
    }
    
    logger.log_execution_end("trigger_lambda", success=False, 
                           metrics={"execution_time": execution_time, "status_code": status_code})
    
    return {
        "statusCode": status_code,
        "body": response_body
    }