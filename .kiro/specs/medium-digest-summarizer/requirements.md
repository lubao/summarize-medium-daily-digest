# Requirements Document

## Introduction

This feature implements an AWS Serverless application using Python and the latest AWS CDK version, developed in a virtual environment (venv). The application automatically processes Medium Daily Digest emails stored in S3, extracts article links, fetches article content using stored Medium cookies, generates AI-powered summaries using AWS Nova, and sends the summaries to a configured Slack channel via webhook. The system is deployed in the us-east-1 region.

## Requirements

### Requirement 1

**User Story:** As a user, I want to store Medium Daily Digest email content in S3 and have it automatically processed, so that I can get summaries of articles with minimal manual effort.

#### Acceptance Criteria

1. WHEN a user uploads Medium Daily Digest email content to the designated S3 bucket THEN the system SHALL automatically trigger processing via S3 event notification
2. WHEN the S3 event is received THEN the system SHALL retrieve the email content from the S3 object
3. WHEN the email content is retrieved THEN the system SHALL parse it to identify and extract all Medium article links
4. IF no article links are found THEN the system SHALL log the event and complete processing with zero articles processed
5. WHEN article links are extracted THEN the system SHALL validate that the links are valid Medium article URLs
6. IF invalid URLs are found THEN the system SHALL filter them out and log the invalid URLs for monitoring

### Requirement 2

**User Story:** As a user, I want the system to fetch full article content from Medium using stored authentication, so that complete article text is available for summarization.

#### Acceptance Criteria

1. WHEN article links are identified THEN the system SHALL retrieve Medium cookies from AWS Secrets Manager in JSON format
2. WHEN Medium cookies are retrieved THEN the system SHALL parse the JSON structure and use the cookies to authenticate requests to Medium articles
3. WHEN fetching article content THEN the system SHALL handle rate limiting and retry failed requests with exponential backoff
4. IF authentication fails THEN the system SHALL log the error and notify administrators
5. WHEN article content is successfully fetched THEN the system SHALL extract the main article text excluding ads and navigation elements
6. WHEN storing Medium cookies THEN the system SHALL use JSON array format with complete cookie objects including domain, expiration, security flags, and values for better maintainability and compatibility

### Requirement 3

**User Story:** As a user, I want the system to generate concise AI summaries of articles, so that I can quickly understand the key points without reading full articles.

#### Acceptance Criteria

1. WHEN article content is extracted THEN the system SHALL send the content to AWS Nova for summarization
2. WHEN requesting summarization THEN the system SHALL configure Nova to generate concise, informative summaries
3. IF Nova API fails THEN the system SHALL retry the request up to 3 times with exponential backoff
4. WHEN summarization is complete THEN the system SHALL validate that the summary is not empty and contains meaningful content
5. IF summarization fails after retries THEN the system SHALL use a fallback summary indicating the article could not be processed

### Requirement 4

**User Story:** As a user, I want summaries to be automatically sent to my Slack channel, so that I can receive them in my preferred communication platform.

#### Acceptance Criteria

1. WHEN article summaries are generated THEN the system SHALL retrieve the Slack webhook URL from AWS Secrets Manager
2. WHEN sending to Slack THEN the system SHALL format the request as application/json with the content in the 'summary' key
3. WHEN formatting each article THEN the system SHALL use the following Markdown format: "📌 *{{title}}*\n\n📝 {{summary}}\n\n🔗 link：{{url}}"
4. WHEN multiple articles are processed THEN the system SHALL send individual messages for each article using the specified format
5. IF Slack webhook fails THEN the system SHALL retry the request up to 3 times with exponential backoff
6. WHEN all summaries are sent THEN the system SHALL log the successful completion of the digest processing

### Requirement 5

**User Story:** As a system administrator, I want secure storage of sensitive credentials, so that Medium cookies and Slack webhooks are protected.

#### Acceptance Criteria

1. WHEN the system needs authentication credentials THEN it SHALL retrieve them from AWS Secrets Manager
2. WHEN storing credentials THEN the system SHALL use appropriate encryption and access controls
3. WHEN storing Medium cookies THEN the system SHALL use JSON array format to structure cookie data with complete cookie objects including domain, expiration, and security properties
4. WHEN credentials are accessed THEN the system SHALL log access attempts for security auditing
5. IF credential retrieval fails THEN the system SHALL fail gracefully and notify administrators
6. WHEN credentials expire THEN the system SHALL provide clear error messages for credential renewal

### Requirement 6

**User Story:** As a developer, I want comprehensive error handling and logging, so that I can monitor system health and troubleshoot issues effectively.

#### Acceptance Criteria

1. WHEN any error occurs THEN the system SHALL log detailed error information including timestamps and context
2. WHEN processing completes THEN the system SHALL log success metrics including number of articles processed
3. IF critical errors occur THEN the system SHALL send notifications to administrators
4. WHEN the system starts processing THEN it SHALL log the initiation with relevant metadata
5. WHEN rate limits are encountered THEN the system SHALL log the rate limiting events and retry attempts

### Requirement 7

**User Story:** As a user, I want a dedicated S3 bucket for email storage with automatic event triggering, so that the system can process emails as soon as they are uploaded.

#### Acceptance Criteria

1. WHEN deploying the infrastructure THEN the system SHALL create a dedicated S3 bucket for storing Medium Daily Digest emails
2. WHEN configuring the S3 bucket THEN the system SHALL enable event notifications for object creation events
3. WHEN an email file is uploaded to the S3 bucket THEN the system SHALL automatically trigger the processing workflow
4. WHEN configuring S3 events THEN the system SHALL filter for relevant file types and prefixes to avoid unnecessary triggers
5. WHEN the system processes an S3 event THEN it SHALL retrieve the email content from the specified S3 object key

### Requirement 8

**User Story:** As a developer, I want to use modern Python development practices with AWS CDK, so that the infrastructure and application code are maintainable and deployable.

#### Acceptance Criteria

1. WHEN setting up the project THEN the system SHALL use a Python virtual environment (venv) for dependency isolation
2. WHEN defining infrastructure THEN the system SHALL use the latest version of AWS CDK with Python bindings
3. WHEN deploying THEN the system SHALL use CDK to provision all AWS resources including Lambda functions, S3 bucket, Secrets Manager, and IAM roles in the us-east-1 region
4. WHEN developing THEN the system SHALL follow Python best practices including type hints and proper error handling
5. WHEN packaging THEN the system SHALL ensure all Python dependencies are properly bundled for Lambda deployment