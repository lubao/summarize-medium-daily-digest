# Medium Digest Summarizer

AWS Serverless application that processes Medium Daily Digest emails, extracts article content, generates AI summaries using AWS Nova, and sends formatted messages to Slack.

## Project Structure

```
├── app.py                          # CDK app entry point
├── cdk.json                        # CDK configuration with medium-digest profile
├── requirements.txt                # Python dependencies
├── requirements-dev.txt            # Development dependencies
├── medium_digest_summarizer/       # CDK stack definition
│   ├── __init__.py
│   └── medium_digest_summarizer_stack.py
├── lambdas/                        # Lambda function implementations
│   ├── trigger/                    # API Gateway trigger Lambda
│   ├── parse_email/                # Email parsing Lambda
│   ├── fetch_articles/             # Article fetching Lambda
│   ├── summarize/                  # AI summarization Lambda
│   └── send_to_slack/              # Slack notification Lambda
├── shared/                         # Shared utilities and data models
└── tests/                          # Unit and integration tests
```

## Setup

1. Create and activate virtual environment:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   pip install -r requirements-dev.txt
   ```

3. Configure AWS profile for deployment:
   ```bash
   aws configure --profile medium-digest
   ```

4. **Configure Secrets** (Required before deployment):
   - Create your Slack webhook URL in your Slack workspace
   - Obtain Medium authentication cookies from your browser
   - Update the CDK stack with your actual values:
     - Replace `REPLACE_WITH_YOUR_SLACK_WEBHOOK_URL` in `medium_digest_summarizer_stack.py`
     - Replace `REPLACE_WITH_YOUR_MEDIUM_COOKIES` in `deploy.py`

## Security

⚠️ **Important Security Notes:**
- This repository has been cleaned of all sensitive authentication data
- Never commit actual webhook URLs or authentication cookies to version control
- Use AWS Secrets Manager for storing sensitive configuration
- The `.gitignore` file is configured to prevent accidental commits of sensitive files

## Deployment

1. Ensure you have configured your secrets (see Setup step 4)
2. Deploy the CDK stack:
   ```bash
   cdk deploy --profile medium-digest
   ```

## Development

The project uses AWS CDK with Python bindings and is configured to use the `medium-digest` AWS profile for deployment.

## Architecture

The system processes Medium Daily Digest emails through a serverless pipeline:
1. **S3 Bucket** - Stores uploaded email files
2. **Step Function** - Orchestrates the processing workflow
3. **Lambda Functions** - Handle parsing, fetching, summarizing, and notifications
4. **AWS Bedrock Nova** - Generates AI-powered article summaries
5. **Slack Integration** - Sends formatted summaries to your Slack channel

## Next Steps

Follow the implementation tasks in `.kiro/specs/medium-digest-summarizer/tasks.md` to build the complete application.