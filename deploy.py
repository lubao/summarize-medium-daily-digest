#!/usr/bin/env python3
"""
Deployment script for Medium Digest Summarizer
This script deploys the CDK stack using the medium-digest profile and sets the required secret values.
"""

import boto3
import subprocess
import sys
import json
import argparse
import os
from datetime import datetime

def run_command(command, description):
    """Run a shell command and handle errors"""
    print(f"\n{description}...")
    try:
        result = subprocess.run(command, shell=True, check=True, capture_output=True, text=True)
        print(f"✅ {description} completed successfully")
        return result.stdout
    except subprocess.CalledProcessError as e:
        print(f"❌ {description} failed:")
        print(f"Error: {e.stderr}")
        sys.exit(1)

def set_secret_value(secret_name, secret_value, description, profile=None):
    """Set a secret value in AWS Secrets Manager"""
    print(f"\nSetting {description}...")
    try:
        session = boto3.Session(profile_name=profile) if profile else boto3.Session()
        secrets_client = session.client('secretsmanager')
        secrets_client.put_secret_value(
            SecretId=secret_name,
            SecretString=secret_value
        )
        print(f"✅ {description} set successfully")
    except Exception as e:
        print(f"❌ Failed to set {description}: {str(e)}")
        sys.exit(1)

def validate_deployment(profile=None):
    """Validate that all resources were created successfully"""
    print("\n🔍 Validating deployment...")
    
    try:
        session = boto3.Session(profile_name=profile) if profile else boto3.Session()
        
        # Check CloudFormation stack
        cf_client = session.client('cloudformation')
        try:
            stack_response = cf_client.describe_stacks(StackName='MediumDigestSummarizerStack')
            stack_status = stack_response['Stacks'][0]['StackStatus']
            if stack_status == 'CREATE_COMPLETE' or stack_status == 'UPDATE_COMPLETE':
                print("✅ CloudFormation stack deployed successfully")
            else:
                print(f"❌ CloudFormation stack status: {stack_status}")
                return False
        except Exception as e:
            print(f"❌ Failed to validate CloudFormation stack: {str(e)}")
            return False
        
        # Check Secrets Manager secrets
        secrets_client = session.client('secretsmanager')
        for secret_name in ['medium-cookies', 'slack-webhook-url']:
            try:
                secrets_client.describe_secret(SecretId=secret_name)
                print(f"✅ Secret '{secret_name}' exists")
            except Exception as e:
                print(f"❌ Secret '{secret_name}' not found: {str(e)}")
                return False
        
        # Check Lambda functions
        lambda_client = session.client('lambda')
        expected_functions = [
            'MediumDigestSummarizerStack-TriggerLambda',
            'MediumDigestSummarizerStack-ParseEmailLambda',
            'MediumDigestSummarizerStack-FetchArticlesLambda',
            'MediumDigestSummarizerStack-SummarizeLambda',
            'MediumDigestSummarizerStack-SendToSlackLambda'
        ]
        
        for function_name in expected_functions:
            try:
                lambda_client.get_function(FunctionName=function_name)
                print(f"✅ Lambda function '{function_name}' exists")
            except Exception as e:
                print(f"❌ Lambda function '{function_name}' not found: {str(e)}")
                return False
        
        # Check Step Function
        sf_client = session.client('stepfunctions')
        try:
            state_machines = sf_client.list_state_machines()
            found_sm = False
            for sm in state_machines['stateMachines']:
                if 'MediumDigestSummarizerStateMachine' in sm['name']:
                    print(f"✅ Step Function state machine exists: {sm['name']}")
                    found_sm = True
                    break
            if not found_sm:
                print("❌ Step Function state machine not found")
                return False
        except Exception as e:
            print(f"❌ Failed to validate Step Function: {str(e)}")
            return False
        
        # Check API Gateway
        apigw_client = session.client('apigateway')
        try:
            apis = apigw_client.get_rest_apis()
            found_api = False
            for api in apis['items']:
                if 'MediumDigestSummarizerAPI' in api['name']:
                    print(f"✅ API Gateway exists: {api['name']}")
                    found_api = True
                    break
            if not found_api:
                print("❌ API Gateway not found")
                return False
        except Exception as e:
            print(f"❌ Failed to validate API Gateway: {str(e)}")
            return False
        
        print("✅ All resources validated successfully")
        return True
        
    except Exception as e:
        print(f"❌ Validation failed: {str(e)}")
        return False

def run_tests(test_type="all", profile=None):
    """Run integration tests after deployment"""
    print(f"\n🧪 Running {test_type} tests...")
    
    # Set profile for tests
    if profile:
        os.environ['AWS_PROFILE'] = profile
    
    test_commands = {
        "unit": "python -m pytest tests/test_*.py -v --tb=short -x --ignore=tests/test_*_integration.py --ignore=tests/test_integration_suite.py --ignore=tests/test_performance.py --ignore=tests/test_deployment_validation.py --ignore=tests/test_end_to_end_integration.py",
        "integration": "python -m pytest tests/test_*_integration.py tests/test_integration_suite.py tests/test_end_to_end_integration.py -v --tb=short",
        "performance": "python -m pytest tests/test_performance.py -v --tb=short -s",
        "deployment": "python -m pytest tests/test_deployment_validation.py -v --tb=short",
        "e2e": "python -m pytest tests/test_end_to_end_integration.py -v --tb=short",
        "ci": "python run_tests.py --ci --profile " + (profile or "medium-digest"),
        "all": "python -m pytest tests/ -v --tb=short"
    }
    
    command = test_commands.get(test_type, test_commands["all"])
    
    try:
        result = subprocess.run(command, shell=True, check=True, capture_output=True, text=True)
        print(f"✅ {test_type.title()} tests passed")
        print(f"Test output:\n{result.stdout}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ {test_type.title()} tests failed:")
        print(f"Error output: {e.stderr}")
        print(f"Standard output: {e.stdout}")
        return False

def generate_deployment_report(profile=None):
    """Generate comprehensive deployment report"""
    print("\n📋 Generating deployment report...")
    
    try:
        session = boto3.Session(profile_name=profile) if profile else boto3.Session()
        
        # Get stack information
        cf_client = session.client('cloudformation')
        stack_response = cf_client.describe_stacks(StackName='MediumDigestSummarizerStack')
        stack = stack_response['Stacks'][0]
        
        # Get stack outputs
        stack_outputs = {
            output['OutputKey']: output['OutputValue'] 
            for output in stack.get('Outputs', [])
        }
        
        # Get stack resources
        resources_response = cf_client.describe_stack_resources(
            StackName='MediumDigestSummarizerStack'
        )
        resources = resources_response['StackResources']
        
        # Generate report
        report_content = f"""# Medium Digest Summarizer - Deployment Report

Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
AWS Profile: {profile or 'default'}
Region: {session.region_name or 'us-east-1'}

## Stack Information

- **Stack Name**: {stack['StackName']}
- **Stack Status**: {stack['StackStatus']}
- **Creation Time**: {stack['CreationTime']}
- **Last Updated**: {stack.get('LastUpdatedTime', 'N/A')}

## Stack Outputs

"""
        
        for key, value in stack_outputs.items():
            report_content += f"- **{key}**: `{value}`\n"
        
        report_content += "\n## Deployed Resources\n\n"
        
        # Group resources by type
        resource_types = {}
        for resource in resources:
            resource_type = resource['ResourceType']
            if resource_type not in resource_types:
                resource_types[resource_type] = []
            resource_types[resource_type].append(resource)
        
        for resource_type, type_resources in sorted(resource_types.items()):
            report_content += f"### {resource_type}\n\n"
            for resource in type_resources:
                report_content += f"- **{resource['LogicalResourceId']}**: {resource['PhysicalResourceId']} ({resource['ResourceStatus']})\n"
            report_content += "\n"
        
        # Add configuration details
        report_content += """## Configuration Details

### Lambda Functions

| Function | Runtime | Memory | Timeout |
|----------|---------|--------|---------|
"""
        
        lambda_client = session.client('lambda')
        lambda_functions = [r for r in resources if r['ResourceType'] == 'AWS::Lambda::Function']
        
        for func_resource in lambda_functions:
            try:
                func_config = lambda_client.get_function(FunctionName=func_resource['PhysicalResourceId'])
                config = func_config['Configuration']
                report_content += f"| {func_resource['LogicalResourceId']} | {config['Runtime']} | {config['MemorySize']}MB | {config['Timeout']}s |\n"
            except Exception:
                report_content += f"| {func_resource['LogicalResourceId']} | N/A | N/A | N/A |\n"
        
        report_content += """
### Secrets Manager

The following secrets are configured:
- `medium-cookies`: Medium authentication cookies
- `slack-webhook-url`: Slack webhook URL for notifications

### API Gateway

"""
        
        if 'ApiGatewayUrl' in stack_outputs:
            report_content += f"- **API Endpoint**: {stack_outputs['ApiGatewayUrl']}\n"
            report_content += f"- **API Key**: {stack_outputs.get('ApiKey', 'N/A')}\n"
            report_content += "- **Rate Limiting**: 10 requests per day per API key\n"
        
        report_content += """
## Usage Instructions

### Testing the Deployment

```bash
# Run deployment validation
python deploy.py --profile """ + (profile or 'medium-digest') + """ --validate-only

# Run comprehensive tests
python deploy.py --profile """ + (profile or 'medium-digest') + """ --validate-only --run-tests ci

# Run performance benchmarks
python benchmark.py --profile """ + (profile or 'medium-digest') + """ --benchmark all
```

### API Usage

```bash
curl -X POST \\
  -H "Content-Type: application/json" \\
  -H "x-api-key: """ + stack_outputs.get('ApiKey', 'YOUR_API_KEY') + """" \\
  -d '{"payload": "{\\"html\\": \\"<a href=\\"https://medium.com/test\\">Test</a>\\"}"}' \\
  """ + stack_outputs.get('ApiGatewayUrl', 'YOUR_API_URL') + """/process-digest
```

## Monitoring

- **CloudWatch Logs**: Check `/aws/lambda/MediumDigestSummarizerStack-*` log groups
- **Step Functions**: Monitor executions in AWS Console
- **API Gateway**: Check usage metrics and throttling

## Next Steps

1. Verify secrets are properly configured
2. Test with sample Medium digest email
3. Monitor CloudWatch logs for any issues
4. Set up CloudWatch alarms for error monitoring

---
*Report generated by Medium Digest Summarizer deployment script*
"""
        
        # Write report to file
        report_filename = f"deployment-report-{datetime.now().strftime('%Y%m%d-%H%M%S')}.md"
        with open(report_filename, 'w') as f:
            f.write(report_content)
        
        print(f"✅ Deployment report generated: {report_filename}")
        
        # Also print summary to console
        print("\n📊 Deployment Summary:")
        print(f"  Stack Status: {stack['StackStatus']}")
        print(f"  Resources: {len(resources)} deployed")
        print(f"  API Endpoint: {stack_outputs.get('ApiGatewayUrl', 'N/A')}")
        print(f"  Report File: {report_filename}")
        
    except Exception as e:
        print(f"❌ Failed to generate deployment report: {str(e)}")

def main():
    parser = argparse.ArgumentParser(description='Deploy Medium Digest Summarizer')
    parser.add_argument('--profile', default='medium-digest', 
                       help='AWS profile to use (default: medium-digest)')
    parser.add_argument('--skip-secrets', action='store_true',
                       help='Skip setting secret values')
    parser.add_argument('--validate-only', action='store_true',
                       help='Only validate existing deployment')
    parser.add_argument('--run-tests', choices=['unit', 'integration', 'performance', 'deployment', 'e2e', 'all', 'ci'],
                       help='Run tests after deployment')
    parser.add_argument('--skip-bootstrap', action='store_true',
                       help='Skip CDK bootstrap step')
    parser.add_argument('--benchmark', action='store_true',
                       help='Run performance benchmarks after deployment')
    parser.add_argument('--generate-report', action='store_true',
                       help='Generate comprehensive deployment report')
    
    args = parser.parse_args()
    
    # Set AWS profile environment variable
    if args.profile:
        os.environ['AWS_PROFILE'] = args.profile
        print(f"🔧 Using AWS profile: {args.profile}")
    
    if args.validate_only:
        print("🔍 Validating existing deployment...")
        if validate_deployment(args.profile):
            print("\n🎉 Deployment validation successful!")
            if args.run_tests:
                run_tests(args.run_tests, args.profile)
        else:
            print("\n❌ Deployment validation failed!")
            sys.exit(1)
        return
    
    print("🚀 Starting Medium Digest Summarizer deployment...")
    
    # Bootstrap CDK if needed
    if not args.skip_bootstrap:
        print("\n🔧 Bootstrapping CDK...")
        bootstrap_cmd = f"cdk bootstrap --profile {args.profile}" if args.profile else "cdk bootstrap"
        try:
            subprocess.run(bootstrap_cmd, shell=True, check=True, capture_output=True, text=True)
            print("✅ CDK bootstrap completed")
        except subprocess.CalledProcessError:
            print("ℹ️ CDK bootstrap may have already been done")
    else:
        print("⏭️ Skipping CDK bootstrap")
    
    # Deploy CDK stack with profile
    deploy_cmd = f"cdk deploy --require-approval never --profile {args.profile}" if args.profile else "cdk deploy --require-approval never"
    run_command(deploy_cmd, "CDK stack deployment")
    
    if not args.skip_secrets:
        # Set secret values
        medium_cookies = "REPLACE_WITH_YOUR_MEDIUM_COOKIES"
        
        slack_webhook_url = "REPLACE_WITH_YOUR_SLACK_WEBHOOK_URL"
        
        set_secret_value("medium-cookies", medium_cookies, "Medium cookies secret", args.profile)
        set_secret_value("slack-webhook-url", slack_webhook_url, "Slack webhook URL secret", args.profile)
    
    # Validate deployment
    if validate_deployment(args.profile):
        print("\n🎉 Deployment completed and validated successfully!")
        print("\nNext steps:")
        print("1. Note down the API Gateway URL from the CDK outputs")
        print("2. Note down the API Key ID from the CDK outputs")
        print("3. Use the API key to authenticate requests to the API Gateway")
        print("4. Run integration tests with: python -m pytest tests/test_*_integration.py -v")
        
        # Run tests if requested
        if args.run_tests:
            if not run_tests(args.run_tests, args.profile):
                print("\n❌ Tests failed after deployment!")
                sys.exit(1)
            else:
                print(f"\n🎉 Deployment and {args.run_tests} tests completed successfully!")
        
        # Run benchmarks if requested
        if args.benchmark:
            print("\n🏁 Running performance benchmarks...")
            try:
                benchmark_cmd = f"python benchmark.py --profile {args.profile} --benchmark all" if args.profile else "python benchmark.py --benchmark all"
                subprocess.run(benchmark_cmd, shell=True, check=True)
                print("✅ Performance benchmarks completed successfully")
            except subprocess.CalledProcessError as e:
                print(f"❌ Performance benchmarks failed: {e}")
        
        # Generate deployment report if requested
        if args.generate_report:
            generate_deployment_report(args.profile)
    else:
        print("\n❌ Deployment completed but validation failed!")
        sys.exit(1)

if __name__ == "__main__":
    main()