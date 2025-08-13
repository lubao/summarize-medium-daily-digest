# Medium Digest Summarizer - Deployment Guide

This guide covers the complete deployment and testing procedures for the Medium Digest Summarizer application.

## Prerequisites

1. **Python Environment**
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   pip install -r requirements-dev.txt
   ```

2. **AWS CLI Configuration**
   ```bash
   # Configure the medium-digest profile
   aws configure --profile medium-digest
   ```
   
   You'll need to provide:
   - AWS Access Key ID
   - AWS Secret Access Key
   - Default region (e.g., us-east-1)
   - Default output format (json)

3. **AWS CDK Bootstrap**
   ```bash
   # Bootstrap CDK for your account/region (one-time setup)
   cdk bootstrap --profile medium-digest
   ```

## Deployment Options

### 1. Full Deployment (Recommended)

Deploy the complete application with secrets and validation:

```bash
python deploy.py --profile medium-digest
```

This will:
- Bootstrap CDK (if needed)
- Deploy all AWS resources
- Set up Secrets Manager with Medium cookies and Slack webhook
- Validate deployment
- Show next steps

### 2. Deployment with Testing

Deploy and run tests automatically:

```bash
# Deploy and run all tests
python deploy.py --profile medium-digest --run-tests all

# Deploy and run specific test types
python deploy.py --profile medium-digest --run-tests integration
python deploy.py --profile medium-digest --run-tests performance
python deploy.py --profile medium-digest --run-tests deployment

# Deploy with CI/CD pipeline testing
python deploy.py --profile medium-digest --run-tests ci

# Deploy with performance benchmarking
python deploy.py --profile medium-digest --benchmark

# Deploy with comprehensive reporting
python deploy.py --profile medium-digest --generate-report
```

### 3. Validation Only

Validate an existing deployment without redeploying:

```bash
python deploy.py --profile medium-digest --validate-only
```

### 4. Advanced Options

```bash
# Skip secrets setup (if already configured)
python deploy.py --profile medium-digest --skip-secrets

# Skip CDK bootstrap (if already done)
python deploy.py --profile medium-digest --skip-bootstrap

# Validate and run tests without deployment
python deploy.py --profile medium-digest --validate-only --run-tests deployment
```

## Manual Deployment Steps

If you prefer manual deployment:

1. **Deploy CDK Stack**
   ```bash
   cdk deploy --profile medium-digest --require-approval never
   ```

2. **Set Secrets**
   ```bash
   # Set Medium cookies
   aws secretsmanager put-secret-value \
     --secret-id medium-cookies \
     --secret-string "your-medium-cookies-here" \
     --profile medium-digest

   # Set Slack webhook URL
   aws secretsmanager put-secret-value \
     --secret-id slack-webhook-url \
     --secret-string "https://hooks.slack.com/your-webhook-url" \
     --profile medium-digest
   ```

3. **Validate Deployment**
   ```bash
   python deploy.py --profile medium-digest --validate-only
   ```

## Testing Procedures

### Test Types

1. **Unit Tests** - Test individual components in isolation
2. **Integration Tests** - Test component interactions and AWS service integrations
3. **End-to-End Tests** - Test complete workflow from email to Slack
4. **Performance Tests** - Test scalability, concurrency, and performance limits
5. **Deployment Validation** - Verify AWS resources are correctly configured
6. **Smoke Tests** - Quick validation of basic functionality

### Using the Test Runners

The project includes multiple test execution tools for different needs:

#### Basic Test Runner (`run_tests.py`)
```bash
# List available test suites
python run_tests.py --list

# Run specific test suites
python run_tests.py unit integration
python run_tests.py performance
python run_tests.py deployment

# Run CI/CD pipeline (recommended for validation)
python run_tests.py --ci

# Run full test suite (includes performance tests)
python run_tests.py --full

# Use different AWS profile
python run_tests.py --profile my-profile unit integration
```

#### Advanced Test Execution Suite (`test_execution_suite.py`)
For comprehensive testing with advanced features:

```bash
# List available test suites with detailed information
./test_execution_suite.py --list

# Run CI/CD pipeline with advanced reporting
./test_execution_suite.py --ci

# Run complete test suite with comprehensive analysis
./test_execution_suite.py --full

# Run specific suites with parallel execution
./test_execution_suite.py unit integration performance --parallel

# Run with fail-fast behavior
./test_execution_suite.py smoke unit integration --fail-fast

# Run without dependency resolution
./test_execution_suite.py unit performance --no-deps

# Use different AWS profile
./test_execution_suite.py --profile my-profile --ci
```

#### Test Suite Categories

- **Fast Tests** (`smoke`, `unit`): Quick validation (< 5 minutes)
- **Medium Tests** (`integration`, `comprehensive`): Moderate execution time (5-15 minutes)
- **Slow Tests** (`e2e`, `performance`): Comprehensive testing (10-30 minutes)
- **Validation Tests** (`deployment`): Infrastructure validation (2-5 minutes)
- **Live Tests** (`live`): Tests with actual AWS services (requires deployment)

### Manual Test Execution

```bash
# Run all tests
python -m pytest tests/ -v

# Run specific test types
python -m pytest tests/test_*_integration.py -v
python -m pytest tests/test_performance.py -v -s
python -m pytest tests/test_deployment_validation.py -v

# Run with live AWS services (requires deployment)
python -m pytest tests/ -v --run-live
```

### Test Suite Details

#### Unit Tests
- Test individual Lambda functions
- Test shared utilities and models
- Test error handling logic
- Fast execution (< 5 minutes)

#### Integration Tests
- Test Lambda function interactions
- Test AWS service integrations (mocked)
- Test error scenarios and recovery
- Medium execution time (5-10 minutes)

#### End-to-End Tests
- Test complete workflow with realistic payloads
- Test concurrent request handling
- Test various email formats and edge cases
- Medium execution time (5-15 minutes)

#### Performance Tests
- Test processing time scaling
- Test memory usage patterns
- Test concurrent load handling
- Test large payload processing
- Longer execution time (10-20 minutes)

#### Deployment Validation Tests
- Verify all AWS resources exist
- Validate resource configurations
- Test IAM permissions
- Test API Gateway setup
- Quick execution (2-5 minutes)

#### Comprehensive Integration Tests
- Complex scenario testing with edge cases
- Unicode and special character handling
- Large batch processing validation
- Memory-intensive payload testing
- Error recovery and resilience testing
- Concurrent request handling
- Authentication failure scenarios
- Medium execution time (10-20 minutes)

#### Smoke Tests
- Quick validation of core functionality
- Basic component health checks
- Fast execution (< 2 minutes)

### Test Data Generation

The test suite includes a comprehensive test data generator:

```python
from tests.test_data_generator import TestDataGenerator

generator = TestDataGenerator()

# Generate sample Medium email with articles
email = generator.generate_medium_email_with_articles(3)

# Generate performance test payload
large_email = generator.generate_performance_test_payload(10)

# Generate concurrent test payloads
payloads = generator.generate_concurrent_test_payloads(5)

# Generate stress test payload
stress_email = generator.generate_stress_test_payload(50)

# Generate edge case payloads
edge_cases = generator.generate_edge_case_payloads()
```

### Automated Test Execution

The project includes automated test execution scripts:

#### Test Runner Script
```bash
# Make executable
chmod +x run_tests.py

# Run CI pipeline
./run_tests.py --ci

# Run specific suites
./run_tests.py unit integration performance

# Run with custom profile
./run_tests.py --profile my-aws-profile deployment
```

#### Integration with Deployment
```bash
# Deploy and run tests automatically
python deploy.py --profile medium-digest --run-tests ci

# Deploy and run full test suite
python deploy.py --profile medium-digest --run-tests all

# Validate existing deployment with tests
python deploy.py --profile medium-digest --validate-only --run-tests deployment

# Deploy with benchmarking and reporting
python deploy.py --profile medium-digest --benchmark --generate-report
```

#### Advanced Test Execution Features

The `test_execution_suite.py` provides advanced testing capabilities:

```bash
# Comprehensive test execution with detailed reporting
./test_execution_suite.py --full

# Parallel execution for faster testing
./test_execution_suite.py unit integration performance --parallel

# Dependency-aware execution
./test_execution_suite.py comprehensive e2e  # Automatically runs prerequisites

# Fail-fast execution for quick feedback
./test_execution_suite.py smoke unit integration --fail-fast

# Generate detailed JSON reports
./test_execution_suite.py --ci  # Automatically generates execution reports
```

#### Test Execution Reports

Both test runners generate comprehensive reports:

- **Console Reports**: Real-time execution status and summary
- **JSON Reports**: Detailed execution metrics and test statistics
- **Performance Analysis**: Execution time analysis and bottleneck identification
- **Deployment Reports**: Infrastructure validation and configuration details

## Configuration

### AWS Profile Setup

The application uses the `medium-digest` AWS profile by default. Configure it with:

```bash
aws configure --profile medium-digest
```

### Environment Variables

You can override the profile using environment variables:

```bash
export AWS_PROFILE=medium-digest
python deploy.py
```

### CDK Context

The CDK configuration is in `cdk.json`:

```json
{
  "app": "python3 app.py",
  "context": {
    "profile": "medium-digest",
    "@aws-cdk/core:enableStackNameDuplicates": true,
    "@aws-cdk/core:stackRelativeExports": true
  }
}
```

## Secrets Configuration

### Medium Cookies

The application requires Medium authentication cookies. Get these by:

1. Log into Medium in your browser
2. Open Developer Tools → Network tab
3. Visit any Medium article
4. Find the request headers and copy the `Cookie` header value
5. Store in AWS Secrets Manager as `medium-cookies`

### Slack Webhook URL

1. Create a Slack app and incoming webhook
2. Copy the webhook URL
3. Store in AWS Secrets Manager as `slack-webhook-url`

## Monitoring and Troubleshooting

### CloudWatch Logs

Each Lambda function creates its own log group:
- `/aws/lambda/MediumDigestSummarizerStack-TriggerLambda-*`
- `/aws/lambda/MediumDigestSummarizerStack-ParseEmailLambda-*`
- `/aws/lambda/MediumDigestSummarizerStack-FetchArticlesLambda-*`
- `/aws/lambda/MediumDigestSummarizerStack-SummarizeLambda-*`
- `/aws/lambda/MediumDigestSummarizerStack-SendToSlackLambda-*`

### Step Function Execution

Monitor Step Function executions in the AWS Console:
1. Go to Step Functions service
2. Find `MediumDigestSummarizerStateMachine`
3. View execution history and details

### API Gateway Testing

Test the API endpoint:

```bash
# Get API details from stack outputs
aws cloudformation describe-stacks \
  --stack-name MediumDigestSummarizerStack \
  --profile medium-digest \
  --query 'Stacks[0].Outputs'

# Test with curl
curl -X POST \
  -H "Content-Type: application/json" \
  -H "x-api-key: YOUR_API_KEY" \
  -d '{"payload": "{\"html\": \"<a href=\"https://medium.com/test\">Test</a>\"}"}' \
  YOUR_API_GATEWAY_URL/process-digest
```

## Performance Considerations

### Concurrency Limits

- **FetchArticles**: Max 5 concurrent executions
- **SummarizeArticles**: Max 3 concurrent executions  
- **SendToSlack**: Max 2 concurrent executions

### Rate Limiting

- API Gateway: 10 requests per day per API key
- Medium requests: Built-in exponential backoff
- Bedrock requests: Built-in retry logic

### Memory and Timeout Settings

- **Trigger Lambda**: 256MB, 30s timeout
- **Parse Email**: 256MB, 2min timeout
- **Fetch Articles**: 512MB, 3min timeout
- **Summarize**: 256MB, 2min timeout
- **Send to Slack**: 256MB, 1min timeout

### Performance Benchmarking

The project includes comprehensive performance benchmarking tools:

```bash
# Run comprehensive benchmark suite
python benchmark.py --benchmark all

# Run specific benchmarks
python benchmark.py --benchmark single --iterations 20
python benchmark.py --benchmark scaling --articles 1 5 10 20 50
python benchmark.py --benchmark concurrent --concurrency 1 2 5 10 20
python benchmark.py --benchmark memory --memory-sizes 1 10 50 100

# Use different AWS profile
python benchmark.py --profile my-profile --benchmark all
```

#### Benchmark Types

1. **Single Article Processing**: Baseline performance metrics
2. **Scaling Performance**: How performance scales with article count
3. **Concurrent Performance**: Throughput under concurrent load
4. **Memory Usage**: Memory consumption patterns

#### Performance Targets

- Single article processing: < 2 seconds average
- Scaling factor: < 5x for 20 articles vs 1 article
- Concurrent throughput: > 1 request/second
- Memory increase: < 100MB for large payloads

## Cleanup

To remove all resources:

```bash
cdk destroy --profile medium-digest
```

This will remove:
- All Lambda functions
- Step Function state machine
- API Gateway
- IAM roles and policies
- CloudWatch log groups

**Note**: Secrets Manager secrets are retained by default for recovery purposes.

## Troubleshooting Common Issues

### 1. CDK Bootstrap Issues

```bash
# Re-run bootstrap with explicit region
cdk bootstrap aws://ACCOUNT-ID/REGION --profile medium-digest
```

### 2. Permission Errors

Ensure your AWS profile has sufficient permissions:
- CloudFormation full access
- Lambda full access
- Step Functions full access
- API Gateway full access
- Secrets Manager full access
- IAM role creation permissions

### 3. Secrets Not Found

```bash
# Verify secrets exist
aws secretsmanager list-secrets --profile medium-digest

# Create missing secrets
aws secretsmanager create-secret \
  --name medium-cookies \
  --secret-string "your-cookies" \
  --profile medium-digest
```

### 4. Test Failures

```bash
# Run tests with verbose output
python -m pytest tests/ -v -s --tb=long

# Run specific failing test
python -m pytest tests/test_specific.py::test_function -v -s
```

### 5. API Gateway 403 Errors

- Verify API key is included in request headers
- Check usage plan limits haven't been exceeded
- Ensure API key is associated with usage plan

## Support

For issues and questions:
1. Check CloudWatch logs for error details
2. Review Step Function execution history
3. Validate all AWS resources are deployed correctly
4. Run deployment validation tests