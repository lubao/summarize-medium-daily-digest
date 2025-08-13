# Medium Digest Summarizer - Testing Guide

This guide provides comprehensive information about testing the Medium Digest Summarizer application, including test types, execution strategies, and best practices.

## Overview

The testing strategy follows a multi-layered approach:

1. **Unit Tests** - Test individual components in isolation
2. **Integration Tests** - Test component interactions
3. **End-to-End Tests** - Test complete workflows
4. **Performance Tests** - Test scalability and performance
5. **Deployment Validation** - Verify infrastructure correctness

## Test Architecture

### Test Structure

```
tests/
├── test_shared_models.py           # Unit tests for data models
├── test_secrets_manager.py         # Unit tests for secrets management
├── test_error_handling.py          # Unit tests for error handling
├── test_parse_email.py             # Unit tests for email parsing
├── test_parse_email_integration.py # Integration tests for email parsing
├── test_fetch_articles.py          # Unit tests for article fetching
├── test_fetch_articles_integration.py # Integration tests for article fetching
├── test_summarize.py               # Unit tests for summarization
├── test_summarize_integration.py   # Integration tests for summarization
├── test_send_to_slack.py           # Unit tests for Slack integration
├── test_send_to_slack_integration.py # Integration tests for Slack
├── test_trigger.py                 # Unit tests for trigger function
├── test_trigger_integration.py     # Integration tests for trigger
├── test_integration_suite.py       # Comprehensive integration tests
├── test_end_to_end_integration.py  # End-to-end workflow tests
├── test_comprehensive_integration.py # Advanced integration scenarios
├── test_performance.py             # Performance and scalability tests
├── test_deployment_validation.py   # Infrastructure validation tests
├── test_data_generator.py          # Test data generation utilities
└── test_error_handling_integration.py # Error scenario integration tests
```

### Test Execution Tools

The project provides multiple test execution tools:

1. **`run_tests.py`**: Basic test runner with organized suite execution
2. **`test_execution_suite.py`**: Advanced test runner with comprehensive reporting
3. **`benchmark.py`**: Performance benchmarking and analysis tool
4. **`deploy.py`**: Deployment script with integrated testing capabilities

### Test Data Generator

The `TestDataGenerator` class provides realistic test data:

```python
from tests.test_data_generator import TestDataGenerator

generator = TestDataGenerator()

# Basic test data
email = generator.generate_medium_email_with_articles(3)
empty_email = generator.generate_medium_email_no_articles()
malformed_email = generator.generate_malformed_email()

# Performance test data
large_payload = generator.generate_performance_test_payload(20)
stress_payload = generator.generate_stress_test_payload(100)
concurrent_payloads = generator.generate_concurrent_test_payloads(10)

# Edge cases
edge_cases = generator.generate_edge_case_payloads()
```

## Test Execution

### Using the Test Runner

The `run_tests.py` script provides organized test execution:

```bash
# List available test suites
python run_tests.py --list

# Run individual suites
python run_tests.py unit
python run_tests.py integration
python run_tests.py performance

# Run multiple suites
python run_tests.py unit integration e2e

# Run CI pipeline
python run_tests.py --ci

# Run full test suite
python run_tests.py --full
```

### Manual Test Execution

```bash
# Run all tests
python -m pytest tests/ -v

# Run specific test files
python -m pytest tests/test_parse_email.py -v
python -m pytest tests/test_*_integration.py -v

# Run with specific markers
python -m pytest tests/ -v -m "not slow"
python -m pytest tests/ -v --run-live  # Requires actual AWS deployment
```

### Test Configuration

#### Environment Variables

```bash
# AWS Profile for testing
export AWS_PROFILE=medium-digest

# Enable live testing (requires deployment)
export RUN_LIVE_TESTS=true

# Test timeout settings
export TEST_TIMEOUT=300
```

#### pytest Configuration

The project uses `pytest.ini` for configuration:

```ini
[tool:pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
addopts = -v --tb=short
markers =
    slow: marks tests as slow (deselect with '-m "not slow"')
    live: marks tests that require live AWS services
    performance: marks performance tests
```

## Test Types in Detail

### Unit Tests

**Purpose**: Test individual components in isolation

**Characteristics**:
- Fast execution (< 30 seconds per test)
- No external dependencies
- Extensive mocking of AWS services
- High code coverage

**Example**:
```python
def test_parse_email_extracts_article_links():
    """Test that email parser correctly extracts Medium article links"""
    from lambdas.parse_email import extract_article_links
    
    html_content = '<a href="https://medium.com/@author/article-123">Article</a>'
    links = extract_article_links(html_content)
    
    assert len(links) == 1
    assert links[0] == "https://medium.com/@author/article-123"
```

### Integration Tests

**Purpose**: Test component interactions and AWS service integrations

**Characteristics**:
- Medium execution time (1-5 minutes per test)
- Mock AWS services but test real interactions
- Test error scenarios and recovery
- Validate data flow between components

**Example**:
```python
def test_complete_article_processing_workflow():
    """Test complete workflow from email parsing to Slack delivery"""
    with patch('boto3.client') as mock_boto:
        # Setup mocks for all AWS services
        setup_aws_mocks(mock_boto)
        
        # Test complete workflow
        result = process_medium_digest(test_email_payload)
        
        assert result['success'] is True
        assert result['articlesProcessed'] > 0
```

### End-to-End Tests

**Purpose**: Test complete workflows with realistic scenarios

**Characteristics**:
- Longer execution time (5-15 minutes)
- Test realistic user scenarios
- Validate complete data flow
- Test error recovery and resilience

**Example**:
```python
def test_complete_digest_processing_workflow():
    """Test processing a complete Medium digest email"""
    # Generate realistic test data
    test_email = generator.generate_medium_email_with_articles(5)
    
    # Process through complete workflow
    result = trigger_lambda_handler(create_api_event(test_email))
    
    # Validate results
    assert result['statusCode'] == 200
    body = json.loads(result['body'])
    assert body['articlesProcessed'] == 5
```

### Performance Tests

**Purpose**: Test scalability, performance limits, and resource usage

**Characteristics**:
- Long execution time (10-30 minutes)
- Test with large payloads
- Measure execution time and memory usage
- Test concurrent processing

**Example**:
```python
def test_concurrent_processing_performance():
    """Test system performance under concurrent load"""
    payloads = generator.generate_concurrent_test_payloads(10)
    
    start_time = time.time()
    
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(process_payload, p) for p in payloads]
        results = [f.result() for f in futures]
    
    execution_time = time.time() - start_time
    
    # All requests should succeed
    assert all(r['success'] for r in results)
    
    # Should complete within reasonable time
    assert execution_time < 60.0
```

### Deployment Validation Tests

**Purpose**: Verify AWS infrastructure is correctly deployed

**Characteristics**:
- Quick execution (1-5 minutes)
- Test actual AWS resources
- Validate configurations and permissions
- Ensure all components are properly connected

**Example**:
```python
def test_lambda_functions_exist_and_configured():
    """Verify all Lambda functions are deployed with correct configuration"""
    lambda_client = boto3.client('lambda')
    
    expected_functions = [
        'medium-digest-trigger',
        'medium-digest-parse-email',
        'medium-digest-fetch-article',
        'medium-digest-summarize',
        'medium-digest-send-to-slack'
    ]
    
    for function_name in expected_functions:
        config = lambda_client.get_function(FunctionName=function_name)
        
        assert config['Configuration']['Runtime'] == 'python3.11'
        assert config['Configuration']['State'] == 'Active'
```

## Test Data and Mocking

### AWS Service Mocking

The tests use comprehensive mocking for AWS services:

```python
def setup_aws_mocks(mock_boto_client):
    """Setup mocks for all AWS services used in tests"""
    
    # Mock Secrets Manager
    mock_secrets = MagicMock()
    mock_secrets.get_secret_value.return_value = {
        'SecretString': 'test-secret-value'
    }
    
    # Mock Bedrock
    mock_bedrock = MagicMock()
    mock_bedrock.invoke_model.return_value = {
        'body': MagicMock(read=lambda: json.dumps({
            'content': [{'text': 'Test summary'}]
        }).encode())
    }
    
    # Mock Step Functions
    mock_stepfunctions = MagicMock()
    mock_stepfunctions.start_sync_execution.return_value = {
        'status': 'SUCCEEDED',
        'output': json.dumps({'articlesProcessed': 3, 'success': True})
    }
    
    def client_factory(service_name, **kwargs):
        if service_name == 'secretsmanager':
            return mock_secrets
        elif service_name == 'bedrock-runtime':
            return mock_bedrock
        elif service_name == 'stepfunctions':
            return mock_stepfunctions
        return MagicMock()
    
    mock_boto_client.side_effect = client_factory
```

### HTTP Request Mocking

External HTTP requests are mocked for consistent testing:

```python
@patch('requests.get')
@patch('requests.post')
def test_article_fetching_and_slack_delivery(mock_post, mock_get):
    """Test article fetching and Slack delivery with mocked HTTP"""
    
    # Mock Medium article fetch
    mock_get.return_value.status_code = 200
    mock_get.return_value.text = generate_test_article_html()
    
    # Mock Slack webhook
    mock_post.return_value.status_code = 200
    mock_post.return_value.json.return_value = {'ok': True}
    
    # Run test
    result = process_article(test_article_url)
    
    assert result['success'] is True
    mock_get.assert_called_once()
    mock_post.assert_called_once()
```

## Test Execution Strategies

### Local Development Testing

```bash
# Quick smoke test during development
python run_tests.py smoke

# Test specific component being developed
python -m pytest tests/test_parse_email.py -v

# Test with coverage
python -m pytest tests/ --cov=lambdas --cov-report=html
```

### CI/CD Pipeline Testing

```bash
# Standard CI pipeline
python run_tests.py --ci

# With deployment validation
python deploy.py --profile ci-profile --run-tests ci
```

### Pre-Production Testing

```bash
# Full test suite including performance
python run_tests.py --full

# With live AWS services
python -m pytest tests/ -v --run-live
```

### Production Validation

```bash
# Deployment validation only
python run_tests.py deployment

# Quick health check
python run_tests.py smoke
```

## Performance Testing Details

### Test Scenarios

1. **Single Article Processing**
   - Measure baseline processing time
   - Test memory usage patterns
   - Validate response times

2. **Multiple Article Scaling**
   - Test with 1, 5, 10, 20 articles
   - Measure scaling characteristics
   - Identify performance bottlenecks

3. **Concurrent Processing**
   - Test with 1, 5, 10 concurrent requests
   - Measure throughput improvements
   - Test resource contention

4. **Large Payload Handling**
   - Test with very large email payloads
   - Measure memory usage scaling
   - Test timeout handling

5. **Stress Testing**
   - Test with 50+ articles
   - Test system limits
   - Validate graceful degradation

### Performance Metrics

- **Execution Time**: Total processing time per request
- **Memory Usage**: Peak memory consumption
- **Throughput**: Requests processed per second
- **Scaling Factor**: Performance ratio with increased load
- **Error Rate**: Percentage of failed requests under load

### Performance Assertions

```python
# Execution time limits
assert avg_execution_time < 5.0, "Average execution time too high"
assert max_execution_time < 10.0, "Maximum execution time too high"

# Scaling limits
scaling_factor = large_load_time / small_load_time
assert scaling_factor < 5.0, "Performance scaling too poor"

# Memory limits
memory_increase = peak_memory - baseline_memory
assert memory_increase < 100.0, "Memory usage increase too high (MB)"

# Throughput requirements
assert throughput > 0.5, "Throughput too low (requests/second)"
```

## Error Testing

### Error Scenarios

1. **Input Validation Errors**
   - Missing payload
   - Invalid JSON format
   - Empty email content

2. **External Service Errors**
   - Medium API failures
   - Bedrock API failures
   - Slack webhook failures

3. **Authentication Errors**
   - Missing secrets
   - Invalid credentials
   - Expired tokens

4. **Network Errors**
   - Connection timeouts
   - DNS resolution failures
   - Rate limiting

### Error Recovery Testing

```python
def test_retry_logic_with_exponential_backoff():
    """Test that retry logic works correctly with exponential backoff"""
    
    with patch('requests.get') as mock_get:
        # First two calls fail, third succeeds
        mock_get.side_effect = [
            requests.exceptions.ConnectionError(),
            requests.exceptions.Timeout(),
            MagicMock(status_code=200, text="Success")
        ]
        
        start_time = time.time()
        result = fetch_with_retry(test_url)
        execution_time = time.time() - start_time
        
        # Should succeed after retries
        assert result is not None
        
        # Should have taken time for backoff
        assert execution_time > 3.0  # 1s + 2s backoff
        
        # Should have made 3 attempts
        assert mock_get.call_count == 3
```

## Best Practices

### Test Organization

1. **Group Related Tests**: Keep tests for the same component together
2. **Use Descriptive Names**: Test names should clearly describe what is being tested
3. **Follow AAA Pattern**: Arrange, Act, Assert
4. **Keep Tests Independent**: Each test should be able to run in isolation

### Mocking Strategy

1. **Mock External Dependencies**: Always mock AWS services and HTTP requests
2. **Use Realistic Mock Data**: Mock responses should match real service responses
3. **Test Error Scenarios**: Mock various failure conditions
4. **Verify Mock Interactions**: Assert that mocks are called correctly

### Performance Testing

1. **Establish Baselines**: Measure performance with known good configurations
2. **Test Realistic Scenarios**: Use realistic data sizes and patterns
3. **Monitor Resource Usage**: Track memory, CPU, and network usage
4. **Set Reasonable Limits**: Define acceptable performance thresholds

### Continuous Integration

1. **Run Tests on Every Commit**: Ensure code quality with automated testing
2. **Use Test Parallelization**: Speed up test execution with parallel runs
3. **Generate Coverage Reports**: Monitor test coverage and identify gaps
4. **Fail Fast**: Stop on first failure for quick feedback

## Troubleshooting

### Common Issues

1. **AWS Credential Issues**
   ```bash
   # Verify AWS profile
   aws sts get-caller-identity --profile medium-digest
   
   # Set environment variable
   export AWS_PROFILE=medium-digest
   ```

2. **Test Timeout Issues**
   ```bash
   # Increase timeout for slow tests
   python -m pytest tests/test_performance.py --timeout=1800
   ```

3. **Mock Setup Issues**
   ```python
   # Ensure mocks are properly configured
   with patch('boto3.client') as mock_client:
       mock_client.return_value = setup_mock_service()
       # Run test
   ```

4. **Import Path Issues**
   ```bash
   # Ensure Python path includes project root
   export PYTHONPATH="${PYTHONPATH}:$(pwd)"
   ```

### Debugging Tests

1. **Use Verbose Output**: Run tests with `-v` flag for detailed output
2. **Add Print Statements**: Use print statements for debugging (remove before commit)
3. **Use Debugger**: Use `pdb` or IDE debugger for complex issues
4. **Check Mock Calls**: Verify that mocks are being called as expected

```python
# Debug mock calls
print(f"Mock called {mock_service.call_count} times")
print(f"Mock called with: {mock_service.call_args_list}")
```

## Conclusion

This comprehensive testing strategy ensures the Medium Digest Summarizer is reliable, performant, and maintainable. The multi-layered approach catches issues at different levels, from individual component failures to system-wide performance problems.

Regular execution of the full test suite, especially before deployments, helps maintain high code quality and system reliability.