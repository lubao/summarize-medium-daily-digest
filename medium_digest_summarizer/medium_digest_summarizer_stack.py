import json
from aws_cdk import (
    Stack,
    aws_lambda as _lambda,
    aws_s3 as s3,
    aws_s3_notifications as s3n,
    aws_stepfunctions as sfn,
    aws_stepfunctions_tasks as tasks,
    aws_secretsmanager as secretsmanager,
    aws_iam as iam,
    aws_logs as logs,
    Duration,
    CfnOutput,
    RemovalPolicy,
    SecretValue,
    BundlingOptions,
)
from constructs import Construct


class MediumDigestSummarizerStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Create Secrets Manager secrets with specific values
        self.medium_cookies_secret = self._create_medium_cookies_secret()
        self.slack_webhook_secret = self._create_slack_webhook_secret()

        # Create S3 bucket for email storage
        self.email_bucket = self._create_email_bucket()

        # Create Lambda functions
        self.trigger_lambda = self._create_trigger_lambda()
        self.parse_email_lambda = self._create_parse_email_lambda()
        self.fetch_article_lambda = self._create_fetch_article_lambda()
        self.summarize_lambda = self._create_summarize_lambda()
        self.send_to_slack_lambda = self._create_send_to_slack_lambda()

        # Create Step Function state machine
        self.state_machine = self._create_state_machine()

        # Configure S3 event notifications
        self._setup_s3_event_notifications()

        # Setup IAM permissions
        self._setup_permissions()

        # Create outputs
        self._create_outputs()

    def _create_lambda_code_with_dependencies(self) -> _lambda.Code:
        """Create Lambda code with Python dependencies bundled"""
        return _lambda.Code.from_asset(
            ".",
            exclude=["cdk.out", ".git", "venv", ".pytest_cache", ".vscode", "*.pyc", "__pycache__"],
            bundling=BundlingOptions(
                image=_lambda.Runtime.PYTHON_3_11.bundling_image,
                command=[
                    "bash", "-c",
                    "pip install -r lambda-requirements.txt -t /asset-output && cp -r lambdas shared *.py /asset-output/"
                ],
            ),
        )

    def _create_medium_cookies_secret(self) -> secretsmanager.Secret:
        """Create Secrets Manager secret for Medium cookies in JSON array format"""
        # Load Medium cookies from external JSON file for easier management
        import os
        cookie_file_path = os.path.join(os.path.dirname(__file__), '..', 'medium-cookie.json')
        
        try:
            with open(cookie_file_path, 'r') as f:
                cookies_data = json.load(f)
            cookies_json = json.dumps(cookies_data)
        except FileNotFoundError:
            # Fallback to hardcoded cookies if file not found
            cookies_json = json.dumps([
                {
                    "domain": "medium.com",
                    "expirationDate": 1755046628.517733,
                    "hostOnly": True,
                    "httpOnly": True,
                    "name": "xsrf",
                    "path": "/",
                    "sameSite": "no_restriction",
                    "secure": True,
                    "session": False,
                    "storeId": None,
                    "value": "DYy2Xwe_OB6t0MCJ"
                },
                {
                    "domain": ".medium.com",
                    "hostOnly": False,
                    "httpOnly": True,
                    "name": "_cfuvid",
                    "path": "/",
                    "sameSite": "no_restriction",
                    "secure": True,
                    "session": True,
                    "storeId": None,
                    "value": "doO4zfjYW_8S9fCSg8yQnkDOpDM1hSSQRvFNMCItpDo-1754960220401-0.0.1.1-604800000"
                },
                {
                    "domain": ".medium.com",
                    "expirationDate": 1789520228.517175,
                    "hostOnly": False,
                    "httpOnly": True,
                    "name": "uid",
                    "path": "/",
                    "sameSite": "no_restriction",
                    "secure": True,
                    "session": False,
                    "storeId": None,
                    "value": "aa1a02b88c89"
                },
                {
                    "domain": ".medium.com",
                    "expirationDate": 1789520228.51752,
                    "hostOnly": False,
                    "httpOnly": True,
                    "name": "sid",
                    "path": "/",
                    "sameSite": "no_restriction",
                    "secure": True,
                    "session": False,
                    "storeId": None,
                    "value": "1:vMh0r+sg1lgvJx3AwsZz7Bawhp0SDkFI/juWT5UuuHmrs/JfU46a0m4qGWnovXjv"
                }
            ])
        
        return secretsmanager.Secret(
            self, "MediumCookiesSecret",
            secret_name="medium-cookies",
            description="Medium authentication cookies in JSON array format for article fetching",
            secret_object_value={
                "cookies": SecretValue.unsafe_plain_text(cookies_json)
            }
        )

    def _create_slack_webhook_secret(self) -> secretsmanager.Secret:
        """Create Secrets Manager secret for Slack webhook URL"""
        return secretsmanager.Secret(
            self, "SlackWebhookSecret",
            secret_name="slack-webhook-url",
            description="Slack webhook URL for sending digest summaries",
            secret_object_value={
                "webhook_url": SecretValue.unsafe_plain_text(
                    "REPLACE_WITH_YOUR_SLACK_WEBHOOK_URL"
                )
            }
        )

    def _create_email_bucket(self) -> s3.Bucket:
        """Create S3 bucket for email storage with event notifications"""
        return s3.Bucket(
            self, "EmailBucket",
            bucket_name=f"medium-digest-emails-{self.account}-{self.region}",
            versioned=True,
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=RemovalPolicy.DESTROY,  # For development - change for production
            auto_delete_objects=True,  # For development - change for production
            lifecycle_rules=[
                s3.LifecycleRule(
                    id="DeleteOldEmails",
                    enabled=True,
                    expiration=Duration.days(30),  # Delete emails after 30 days
                    noncurrent_version_expiration=Duration.days(7)
                )
            ]
        )

    def _create_trigger_lambda(self) -> _lambda.Function:
        """Create Trigger Lambda function for S3 event integration"""
        return _lambda.Function(
            self, "TriggerLambda",
            function_name="medium-digest-trigger",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="lambdas.trigger.lambda_handler",
            code=self._create_lambda_code_with_dependencies(),
            memory_size=256,
            timeout=Duration.seconds(30),
            environment={
                "STATE_MACHINE_ARN": "",  # Will be set after state machine creation
            }
        )

    def _create_parse_email_lambda(self) -> _lambda.Function:
        """Create Parse Email Lambda function"""
        return _lambda.Function(
            self, "ParseEmailLambda",
            function_name="medium-digest-parse-email",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="lambdas.parse_email.lambda_handler",
            code=self._create_lambda_code_with_dependencies(),
            memory_size=256,
            timeout=Duration.minutes(2),
        )

    def _create_fetch_article_lambda(self) -> _lambda.Function:
        """Create Fetch Article Lambda function"""
        return _lambda.Function(
            self, "FetchArticleLambda",
            function_name="medium-digest-fetch-article",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="lambdas.fetch_articles.lambda_handler",
            code=self._create_lambda_code_with_dependencies(),
            memory_size=512,
            timeout=Duration.minutes(3),
            environment={
                "MEDIUM_COOKIES_SECRET_NAME": self.medium_cookies_secret.secret_name,
            }
        )

    def _create_summarize_lambda(self) -> _lambda.Function:
        """Create Summarize Lambda function"""
        return _lambda.Function(
            self, "SummarizeLambda",
            function_name="medium-digest-summarize",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="lambdas.summarize.lambda_handler",
            code=self._create_lambda_code_with_dependencies(),
            memory_size=256,
            timeout=Duration.minutes(2),
        )

    def _create_send_to_slack_lambda(self) -> _lambda.Function:
        """Create Send to Slack Lambda function"""
        return _lambda.Function(
            self, "SendToSlackLambda",
            function_name="medium-digest-send-to-slack",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="lambdas.send_to_slack.lambda_handler",
            code=self._create_lambda_code_with_dependencies(),
            memory_size=256,
            timeout=Duration.minutes(1),
            environment={
                "SLACK_WEBHOOK_SECRET_NAME": self.slack_webhook_secret.secret_name,
            }
        )

    def _create_state_machine(self) -> sfn.StateMachine:
        """Create Step Function state machine with Express workflow"""
        # Load the step function definition
        with open("step_function_definition.json", "r") as f:
            definition_template = f.read()

        # Replace placeholders with actual Lambda ARNs
        definition_json = definition_template.replace(
            "${ParseEmailLambdaArn}", self.parse_email_lambda.function_arn
        ).replace(
            "${FetchArticleLambdaArn}", self.fetch_article_lambda.function_arn
        ).replace(
            "${SummarizeLambdaArn}", self.summarize_lambda.function_arn
        ).replace(
            "${SendToSlackLambdaArn}", self.send_to_slack_lambda.function_arn
        )


        
        # Create CloudWatch log group for Step Function
        log_group = logs.LogGroup(
            self, "StateMachineLogGroup",
            log_group_name="/aws/stepfunctions/medium-digest-summarizer",
            retention=logs.RetentionDays.ONE_WEEK
        )

        # Create the state machine
        state_machine = sfn.StateMachine(
            self, "MediumDigestStateMachine",
            state_machine_name="medium-digest-summarizer",
            state_machine_type=sfn.StateMachineType.EXPRESS,
            definition_body=sfn.DefinitionBody.from_string(definition_json),
            logs=sfn.LogOptions(
                destination=log_group,
                level=sfn.LogLevel.ALL,
                include_execution_data=True
            ),
            tracing_enabled=True,
        )

        # Update trigger lambda environment with state machine ARN
        self.trigger_lambda.add_environment("STATE_MACHINE_ARN", state_machine.state_machine_arn)

        return state_machine

    def _setup_s3_event_notifications(self):
        """Configure S3 event notifications to trigger the processing workflow"""
        # Add S3 event notification to trigger Lambda function for all object creation events
        # This handles email files with or without extensions
        self.email_bucket.add_event_notification(
            s3.EventType.OBJECT_CREATED,
            s3n.LambdaDestination(self.trigger_lambda)
            # No filter - triggers on all files including those without extensions
        )



    def _setup_permissions(self):
        """Setup IAM roles and permissions for all services"""
        
        # Create Lambda execution roles for each function with minimal required permissions
        self._create_lambda_execution_roles()
        
        # Set up Step Function execution role with Lambda invocation permissions
        self._create_step_function_execution_role()
        
        # Configure Bedrock access permissions for Summarize Lambda
        self._configure_bedrock_permissions()
        
        # Add Secrets Manager read permissions for relevant Lambda functions
        self._configure_secrets_manager_permissions()
        
        # Set up CloudWatch logging permissions for all services
        self._setup_cloudwatch_logging_permissions()
        
        # Add S3 read permissions for Trigger Lambda to access email objects
        self._configure_s3_permissions()
        
        # Configure Step Function execution permissions
        self._configure_step_function_permissions()

    def _create_lambda_execution_roles(self):
        """Create Lambda execution roles for each function with minimal required permissions"""
        
        # Each Lambda function already has its own execution role created by CDK
        # We'll add specific permissions to each role based on function requirements
        
        # Trigger Lambda permissions:
        # - CloudWatch Logs (handled in _setup_cloudwatch_logging_permissions)
        # - S3 read access (handled in _configure_s3_permissions)
        # - Step Functions execution (handled in _configure_step_function_permissions)
        
        # Parse Email Lambda permissions:
        # - CloudWatch Logs (handled in _setup_cloudwatch_logging_permissions)
        # - No additional permissions needed for parsing email content
        
        # Fetch Article Lambda permissions:
        # - CloudWatch Logs (handled in _setup_cloudwatch_logging_permissions)
        # - Secrets Manager read for Medium cookies (handled in _configure_secrets_manager_permissions)
        
        # Summarize Lambda permissions:
        # - CloudWatch Logs (handled in _setup_cloudwatch_logging_permissions)
        # - Bedrock access (handled in _configure_bedrock_permissions)
        
        # Send to Slack Lambda permissions:
        # - CloudWatch Logs (handled in _setup_cloudwatch_logging_permissions)
        # - Secrets Manager read for Slack webhook (handled in _configure_secrets_manager_permissions)
        
        pass  # All permissions are configured in specific methods

    def _create_step_function_execution_role(self):
        """Set up Step Function execution role with Lambda invocation permissions"""
        
        # Grant Step Function permissions to invoke all Lambda functions
        # This provides minimal required permissions for the state machine to execute
        self.parse_email_lambda.grant_invoke(self.state_machine.role)
        self.fetch_article_lambda.grant_invoke(self.state_machine.role)
        self.summarize_lambda.grant_invoke(self.state_machine.role)
        self.send_to_slack_lambda.grant_invoke(self.state_machine.role)

        # Add CloudWatch logging permissions for Step Function
        step_function_logs_policy = iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=[
                "logs:CreateLogGroup",
                "logs:CreateLogStream", 
                "logs:PutLogEvents",
                "logs:DescribeLogGroups",
                "logs:DescribeLogStreams"
            ],
            resources=[
                f"arn:aws:logs:{self.region}:{self.account}:log-group:/aws/stepfunctions/*"
            ]
        )
        self.state_machine.role.add_to_policy(step_function_logs_policy)

        # Add X-Ray tracing permissions for Step Function monitoring
        xray_policy = iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=[
                "xray:PutTraceSegments",
                "xray:PutTelemetryRecords",
                "xray:GetSamplingRules",
                "xray:GetSamplingTargets"
            ],
            resources=["*"]
        )
        self.state_machine.role.add_to_policy(xray_policy)



    def _configure_bedrock_permissions(self):
        """Configure Bedrock access permissions for Summarize Lambda"""
        
        # Grant Bedrock permissions to Summarize Lambda for AI summarization
        bedrock_policy = iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=[
                "bedrock:InvokeModel",
                "bedrock:InvokeModelWithResponseStream"
            ],
            resources=[
                f"arn:aws:bedrock:{self.region}::foundation-model/amazon.nova-pro-v1:0"
            ]
        )
        self.summarize_lambda.add_to_role_policy(bedrock_policy)

    def _configure_secrets_manager_permissions(self):
        """Add Secrets Manager read permissions for relevant Lambda functions"""
        
        # Grant Fetch Article Lambda access to Medium cookies secret
        self.medium_cookies_secret.grant_read(self.fetch_article_lambda)
        
        # Grant Send to Slack Lambda access to Slack webhook secret
        self.slack_webhook_secret.grant_read(self.send_to_slack_lambda)

    def _configure_s3_permissions(self):
        """Add S3 read permissions for Trigger Lambda to access email objects"""
        
        # Grant Trigger Lambda permission to read email objects from S3 bucket
        self.email_bucket.grant_read(self.trigger_lambda)
        
        # Grant S3 service permission to invoke Trigger Lambda for event notifications
        self.trigger_lambda.grant_invoke(
            iam.ServicePrincipal("s3.amazonaws.com")
        )

    def _configure_step_function_permissions(self):
        """Configure Step Function execution permissions"""
        
        # Grant Trigger Lambda permission to start Step Function execution
        step_function_policy = iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=[
                "states:StartSyncExecution"
            ],
            resources=[self.state_machine.state_machine_arn]
        )
        self.trigger_lambda.add_to_role_policy(step_function_policy)

    def _setup_cloudwatch_logging_permissions(self):
        """Set up CloudWatch logging permissions for all services"""
        
        # Base CloudWatch Logs policy for all Lambda functions
        cloudwatch_logs_policy = iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=[
                "logs:CreateLogGroup",
                "logs:CreateLogStream",
                "logs:PutLogEvents"
            ],
            resources=[
                f"arn:aws:logs:{self.region}:{self.account}:log-group:/aws/lambda/*"
            ]
        )

        # Add CloudWatch logging permissions to all Lambda functions
        for lambda_function in [
            self.trigger_lambda,
            self.parse_email_lambda,
            self.fetch_article_lambda,
            self.summarize_lambda,
            self.send_to_slack_lambda
        ]:
            lambda_function.add_to_role_policy(cloudwatch_logs_policy)
        
        # Additional CloudWatch permissions for monitoring and metrics
        cloudwatch_metrics_policy = iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=[
                "cloudwatch:PutMetricData"
            ],
            resources=["*"]
        )

        # Add metrics permissions to all Lambda functions
        for lambda_function in [
            self.trigger_lambda,
            self.parse_email_lambda,
            self.fetch_article_lambda,
            self.summarize_lambda,
            self.send_to_slack_lambda
        ]:
            lambda_function.add_to_role_policy(cloudwatch_metrics_policy)

    def _create_outputs(self):
        """Create CloudFormation outputs for important resources"""
        CfnOutput(
            self, "EmailBucketName",
            value=self.email_bucket.bucket_name,
            description="S3 bucket name for storing Medium Daily Digest emails"
        )

        CfnOutput(
            self, "EmailBucketArn",
            value=self.email_bucket.bucket_arn,
            description="S3 bucket ARN for storing Medium Daily Digest emails"
        )

        CfnOutput(
            self, "StateMachineArn",
            value=self.state_machine.state_machine_arn,
            description="Step Function State Machine ARN"
        )

        CfnOutput(
            self, "TriggerLambdaArn",
            value=self.trigger_lambda.function_arn,
            description="Trigger Lambda Function ARN"
        )

        CfnOutput(
            self, "MediumCookiesSecretArn",
            value=self.medium_cookies_secret.secret_arn,
            description="Medium Cookies Secret ARN"
        )

        CfnOutput(
            self, "SlackWebhookSecretArn",
            value=self.slack_webhook_secret.secret_arn,
            description="Slack Webhook Secret ARN"
        )