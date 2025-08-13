# Step Function Configuration

## Overview

This document describes the Step Function state machine definition for the Medium Digest Summarizer workflow. The state machine is configured as an Express workflow for faster execution and lower cost, suitable for synchronous API Gateway integration.

## Workflow Type

- **Type**: Express Workflow
- **Execution Mode**: Synchronous (for API Gateway integration)
- **Billing**: Per request (not per state transition)
- **Duration Limit**: 5 minutes maximum
- **History**: Limited logging for cost optimization

## State Machine Architecture

### 1. ParseEmail State
- **Type**: Task (Lambda invocation)
- **Function**: Parse email content and extract article URLs
- **Retry Policy**: 3 attempts with exponential backoff
- **Error Handling**: Catch all errors and route to HandleParseError
- **Next State**: CheckParseResults

### 2. CheckParseResults State
- **Type**: Choice
- **Purpose**: Validate that articles were found in email
- **Condition**: Check if articles array is present
- **Success Path**: FetchArticles
- **Failure Path**: NoArticlesFound

### 3. FetchArticles State
- **Type**: Map (Parallel processing)
- **Max Concurrency**: 5 (to respect Medium rate limits)
- **Iterator**: FetchSingleArticle task
- **Retry Policy**: 3 attempts with longer intervals for rate limiting
- **Error Handling**: Individual article failures don't stop the workflow
- **Next State**: FilterSuccessfulFetches

### 4. FilterSuccessfulFetches State
- **Type**: Pass (Data transformation)
- **Purpose**: Filter out failed article fetches
- **Logic**: Keep only articles with title field present
- **Next State**: CheckFetchedArticles

### 5. CheckFetchedArticles State
- **Type**: Choice
- **Purpose**: Ensure at least one article was fetched successfully
- **Success Path**: SummarizeArticles
- **Failure Path**: NoArticlesFetched

### 6. SummarizeArticles State
- **Type**: Map (Parallel processing)
- **Max Concurrency**: 3 (to manage Bedrock API limits)
- **Iterator**: SummarizeSingleArticle task
- **Retry Policy**: 3 attempts with longer intervals for AI API
- **Error Handling**: Failed summaries get fallback text
- **Next State**: FilterSuccessfulSummaries

### 7. FilterSuccessfulSummaries State
- **Type**: Pass (Data transformation)
- **Purpose**: Filter out failed summarizations
- **Logic**: Keep only articles with summary field present
- **Next State**: CheckSummarizedArticles

### 8. CheckSummarizedArticles State
- **Type**: Choice
- **Purpose**: Ensure at least one summary was generated
- **Success Path**: SendToSlack
- **Failure Path**: NoSummariesGenerated

### 9. SendToSlack State
- **Type**: Map (Parallel processing)
- **Max Concurrency**: 2 (to avoid overwhelming Slack webhook)
- **Iterator**: SendSingleMessage task
- **Retry Policy**: 3 attempts for webhook failures
- **Error Handling**: Individual message failures are logged
- **Next State**: ProcessingComplete

### 10. ProcessingComplete State
- **Type**: Pass (Final response)
- **Purpose**: Format successful completion response
- **Output**: Status, message, article counts, execution time

## Error Handling States

### HandleParseError
- **Trigger**: Email parsing failures
- **Response**: 400 status with parse error details

### HandleFetchError
- **Trigger**: Critical failures in article fetching
- **Response**: 500 status with fetch error details

### HandleSummarizeError
- **Trigger**: Critical failures in summarization
- **Response**: 500 status with summarization error details

### HandleSlackError
- **Trigger**: Critical failures in Slack messaging
- **Response**: 500 status with Slack error details

## Partial Success States

### NoArticlesFound
- **Trigger**: No articles found in email
- **Response**: 200 status with zero articles processed

### NoArticlesFetched
- **Trigger**: All article fetch attempts failed
- **Response**: 206 status (partial content) with error details

### NoSummariesGenerated
- **Trigger**: All summarization attempts failed
- **Response**: 206 status with error details

## Retry Policies

### Lambda Service Errors
- **Errors**: Lambda.ServiceException, Lambda.AWSLambdaException, Lambda.SdkClientException
- **Interval**: 2 seconds
- **Max Attempts**: 3
- **Backoff Rate**: 2.0

### Task Failures
- **Errors**: States.TaskFailed
- **Interval**: Varies by task (1-5 seconds)
- **Max Attempts**: 2-3
- **Backoff Rate**: 2.0

## Concurrency Limits

### FetchArticles Map State
- **Max Concurrency**: 5
- **Reason**: Respect Medium API rate limits
- **Impact**: Prevents 429 rate limit errors

### SummarizeArticles Map State
- **Max Concurrency**: 3
- **Reason**: Manage Bedrock API quotas and costs
- **Impact**: Prevents throttling and controls costs

### SendToSlack Map State
- **Max Concurrency**: 2
- **Reason**: Avoid overwhelming Slack webhook
- **Impact**: Ensures reliable message delivery

## CDK Integration

### Lambda Function ARN Substitution
The state machine definition uses placeholder ARNs that will be substituted during CDK deployment:

- `${ParseEmailLambdaArn}`: Parse email Lambda function ARN
- `${FetchArticleLambdaArn}`: Fetch article Lambda function ARN
- `${SummarizeLambdaArn}`: Summarize Lambda function ARN
- `${SendToSlackLambdaArn}`: Send to Slack Lambda function ARN

### CDK Stack Implementation
```python
# In the CDK stack
state_machine_definition = self._load_state_machine_definition()
state_machine_definition = state_machine_definition.replace(
    "${ParseEmailLambdaArn}", self.parse_email_lambda.function_arn
)
# ... repeat for other Lambda functions

self.state_machine = sfn.StateMachine(
    self, "MediumDigestStateMachine",
    definition_body=sfn.DefinitionBody.from_string(state_machine_definition),
    state_machine_type=sfn.StateMachineType.EXPRESS,
    logs=sfn.LogOptions(
        destination=logs.LogGroup(self, "StateMachineLogGroup"),
        level=sfn.LogLevel.ERROR
    )
)
```

## Monitoring and Logging

### CloudWatch Integration
- **Log Level**: ERROR (for Express workflows)
- **Log Group**: Dedicated log group for state machine
- **Metrics**: Execution count, duration, success/failure rates

### Error Tracking
- All error states include detailed error information
- Failed executions are logged with context
- Admin notifications can be triggered from error states

## Performance Characteristics

### Expected Execution Time
- **Typical**: 30-60 seconds for 3-5 articles
- **Maximum**: 5 minutes (Express workflow limit)
- **Factors**: Article count, content length, API response times

### Cost Optimization
- Express workflow reduces per-transition costs
- Concurrency limits prevent excessive parallel executions
- Error handling prevents unnecessary retries

## Requirements Mapping

This Step Function definition addresses the following requirements:

- **Requirement 1.3**: Orchestrates email parsing and article extraction
- **Requirement 2.3**: Handles rate limiting for Medium API requests
- **Requirement 3.1**: Manages AI summarization workflow
- **Requirement 4.4**: Coordinates Slack message delivery
- **Requirement 6.1**: Implements comprehensive error handling and logging