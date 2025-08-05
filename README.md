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

## Development

The project uses AWS CDK with Python bindings and is configured to use the `medium-digest` AWS profile for deployment.

## Next Steps

Follow the implementation tasks in `.kiro/specs/medium-digest-summarizer/tasks.md` to build the complete application.