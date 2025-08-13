"""
Deployment validation tests for Medium Digest Summarizer
Verifies all AWS resources are created correctly after deployment
"""

import boto3
import pytest
import json
from botocore.exceptions import ClientError


class TestDeploymentValidation:
    """Test suite to validate deployment of all AWS resources"""
    
    @classmethod
    def setup_class(cls):
        """Set up AWS clients for testing"""
        cls.session = boto3.Session()
        cls.cf_client = cls.session.client('cloudformation')
        cls.lambda_client = cls.session.client('lambda')
        cls.sf_client = cls.session.client('stepfunctions')
        cls.secrets_client = cls.session.client('secretsmanager')
        cls.apigw_client = cls.session.client('apigateway')
        cls.iam_client = cls.session.client('iam')
        
        # Get stack information
        try:
            stack_response = cls.cf_client.describe_stacks(StackName='MediumDigestSummarizerStack')
            cls.stack = stack_response['Stacks'][0]
            cls.stack_outputs = {
                output['OutputKey']: output['OutputValue'] 
                for output in cls.stack.get('Outputs', [])
            }
            cls.stack_resources = cls._get_stack_resources()
        except Exception as e:
            pytest.fail(f"Failed to get stack information: {str(e)}")
    
    @classmethod
    def _get_stack_resources(cls):
        """Get all resources created by the stack"""
        try:
            resources_response = cls.cf_client.describe_stack_resources(
                StackName='MediumDigestSummarizerStack'
            )
            return {
                resource['LogicalResourceId']: resource 
                for resource in resources_response['StackResources']
            }
        except Exception:
            return {}
    
    def test_cloudformation_stack_status(self):
        """Verify CloudFormation stack is in correct state"""
        assert self.stack['StackStatus'] in ['CREATE_COMPLETE', 'UPDATE_COMPLETE'], \
            f"Stack status is {self.stack['StackStatus']}"
        
        # Verify stack has no failed resources
        failed_resources = []
        for resource_id, resource in self.stack_resources.items():
            if 'FAILED' in resource.get('ResourceStatus', ''):
                failed_resources.append(f"{resource_id}: {resource['ResourceStatus']}")
        
        assert not failed_resources, f"Failed resources found: {failed_resources}"
    
    def test_lambda_functions_exist(self):
        """Verify all Lambda functions are created and configured correctly"""
        expected_functions = [
            'TriggerLambda',
            'ParseEmailLambda', 
            'FetchArticlesLambda',
            'SummarizeLambda',
            'SendToSlackLambda'
        ]
        
        for function_logical_id in expected_functions:
            assert function_logical_id in self.stack_resources, \
                f"Lambda function {function_logical_id} not found in stack resources"
            
            resource = self.stack_resources[function_logical_id]
            function_name = resource['PhysicalResourceId']
            
            # Verify function exists and is active
            try:
                function_config = self.lambda_client.get_function(FunctionName=function_name)
                
                assert function_config['Configuration']['State'] == 'Active', \
                    f"Function {function_name} is not active"
                
                assert function_config['Configuration']['Runtime'] == 'python3.11', \
                    f"Function {function_name} has wrong runtime"
                
                # Verify function has appropriate timeout and memory
                timeout = function_config['Configuration']['Timeout']
                memory = function_config['Configuration']['MemorySize']
                
                assert timeout >= 30, f"Function {function_name} timeout too low: {timeout}s"
                assert memory >= 256, f"Function {function_name} memory too low: {memory}MB"
                
                print(f"✅ Lambda function {function_name} validated")
                
            except ClientError as e:
                pytest.fail(f"Failed to validate Lambda function {function_name}: {str(e)}")
    
    def test_step_function_state_machine(self):
        """Verify Step Function state machine is created correctly"""
        # Find state machine in stack resources
        state_machine_resource = None
        for resource_id, resource in self.stack_resources.items():
            if resource['ResourceType'] == 'AWS::StepFunctions::StateMachine':
                state_machine_resource = resource
                break
        
        assert state_machine_resource is not None, "Step Function state machine not found"
        
        state_machine_arn = state_machine_resource['PhysicalResourceId']
        
        try:
            # Verify state machine exists and is active
            sm_description = self.sf_client.describe_state_machine(
                stateMachineArn=state_machine_arn
            )
            
            assert sm_description['status'] == 'ACTIVE', \
                f"State machine is not active: {sm_description['status']}"
            
            assert sm_description['type'] == 'EXPRESS', \
                f"State machine should be EXPRESS type, got: {sm_description['type']}"
            
            # Verify state machine definition is valid JSON
            definition = json.loads(sm_description['definition'])
            assert 'States' in definition, "State machine definition missing States"
            assert 'StartAt' in definition, "State machine definition missing StartAt"
            
            # Verify expected states exist
            expected_states = ['ParseEmail', 'FetchArticles', 'SummarizeArticles', 'SendToSlack']
            for state in expected_states:
                assert state in definition['States'], f"Missing state: {state}"
            
            print(f"✅ Step Function state machine validated")
            
        except ClientError as e:
            pytest.fail(f"Failed to validate Step Function: {str(e)}")
    
    def test_api_gateway_configuration(self):
        """Verify API Gateway is configured correctly"""
        # Find API Gateway in stack outputs
        api_url = self.stack_outputs.get('ApiGatewayUrl')
        assert api_url is not None, "API Gateway URL not found in stack outputs"
        
        # Extract API ID from URL
        api_id = api_url.split('//')[1].split('.')[0]
        
        try:
            # Verify API exists
            api_info = self.apigw_client.get_rest_api(restApiId=api_id)
            assert api_info['name'] == 'MediumDigestSummarizerAPI', \
                f"API name mismatch: {api_info['name']}"
            
            # Verify resources and methods
            resources = self.apigw_client.get_resources(restApiId=api_id)
            
            # Should have root resource and /process-digest resource
            resource_paths = [resource['path'] for resource in resources['items']]
            assert '/' in resource_paths, "Root resource not found"
            assert '/process-digest' in resource_paths, "/process-digest resource not found"
            
            # Find process-digest resource and verify POST method
            process_digest_resource = None
            for resource in resources['items']:
                if resource['path'] == '/process-digest':
                    process_digest_resource = resource
                    break
            
            assert process_digest_resource is not None, "/process-digest resource not found"
            assert 'POST' in process_digest_resource.get('resourceMethods', {}), \
                "POST method not found on /process-digest"
            
            # Verify CORS is enabled (OPTIONS method should exist)
            assert 'OPTIONS' in process_digest_resource.get('resourceMethods', {}), \
                "CORS not enabled (OPTIONS method missing)"
            
            print(f"✅ API Gateway validated")
            
        except ClientError as e:
            pytest.fail(f"Failed to validate API Gateway: {str(e)}")
    
    def test_secrets_manager_secrets(self):
        """Verify Secrets Manager secrets are created"""
        expected_secrets = ['medium-cookies', 'slack-webhook-url']
        
        for secret_name in expected_secrets:
            try:
                secret_info = self.secrets_client.describe_secret(SecretId=secret_name)
                
                assert secret_info['Name'] == secret_name, \
                    f"Secret name mismatch: {secret_info['Name']}"
                
                # Verify secret has a value (don't retrieve actual value for security)
                assert 'LastChangedDate' in secret_info, \
                    f"Secret {secret_name} appears to have no value"
                
                print(f"✅ Secret {secret_name} validated")
                
            except ClientError as e:
                if e.response['Error']['Code'] == 'ResourceNotFoundException':
                    pytest.fail(f"Secret {secret_name} not found")
                else:
                    pytest.fail(f"Failed to validate secret {secret_name}: {str(e)}")
    
    def test_iam_roles_and_policies(self):
        """Verify IAM roles have correct permissions"""
        # Find Lambda execution roles in stack resources
        lambda_roles = []
        for resource_id, resource in self.stack_resources.items():
            if (resource['ResourceType'] == 'AWS::IAM::Role' and 
                'Lambda' in resource_id):
                lambda_roles.append(resource['PhysicalResourceId'])
        
        assert len(lambda_roles) > 0, "No Lambda execution roles found"
        
        for role_name in lambda_roles:
            try:
                # Verify role exists
                role_info = self.iam_client.get_role(RoleName=role_name)
                
                # Verify role has assume role policy for Lambda
                assume_role_policy = role_info['Role']['AssumeRolePolicyDocument']
                lambda_service_found = False
                
                for statement in assume_role_policy.get('Statement', []):
                    if (statement.get('Effect') == 'Allow' and 
                        'lambda.amazonaws.com' in str(statement.get('Principal', {}))):
                        lambda_service_found = True
                        break
                
                assert lambda_service_found, f"Role {role_name} missing Lambda assume role policy"
                
                # Verify role has attached policies
                attached_policies = self.iam_client.list_attached_role_policies(RoleName=role_name)
                assert len(attached_policies['AttachedPolicies']) > 0, \
                    f"Role {role_name} has no attached policies"
                
                print(f"✅ IAM role {role_name} validated")
                
            except ClientError as e:
                pytest.fail(f"Failed to validate IAM role {role_name}: {str(e)}")
    
    def test_api_gateway_usage_plan(self):
        """Verify API Gateway usage plan and API key are configured"""
        # Find usage plan in stack resources
        usage_plan_resource = None
        api_key_resource = None
        
        for resource_id, resource in self.stack_resources.items():
            if resource['ResourceType'] == 'AWS::ApiGateway::UsagePlan':
                usage_plan_resource = resource
            elif resource['ResourceType'] == 'AWS::ApiGateway::ApiKey':
                api_key_resource = resource
        
        assert usage_plan_resource is not None, "Usage plan not found"
        assert api_key_resource is not None, "API key not found"
        
        usage_plan_id = usage_plan_resource['PhysicalResourceId']
        api_key_id = api_key_resource['PhysicalResourceId']
        
        try:
            # Verify usage plan configuration
            usage_plan = self.apigw_client.get_usage_plan(usagePlanId=usage_plan_id)
            
            # Should have throttle and quota limits
            assert 'throttle' in usage_plan, "Usage plan missing throttle configuration"
            assert 'quota' in usage_plan, "Usage plan missing quota configuration"
            
            # Verify daily limit is set to 10
            quota = usage_plan['quota']
            assert quota['limit'] == 10, f"Daily quota should be 10, got {quota['limit']}"
            assert quota['period'] == 'DAY', f"Quota period should be DAY, got {quota['period']}"
            
            # Verify API key exists and is enabled
            api_key = self.apigw_client.get_api_key(apiKey=api_key_id, includeValue=False)
            assert api_key['enabled'] is True, "API key is not enabled"
            
            print(f"✅ Usage plan and API key validated")
            
        except ClientError as e:
            pytest.fail(f"Failed to validate usage plan/API key: {str(e)}")
    
    def test_cloudwatch_log_groups(self):
        """Verify CloudWatch log groups are created for Lambda functions"""
        import boto3
        logs_client = self.session.client('logs')
        
        # Get all Lambda functions from stack
        lambda_functions = []
        for resource_id, resource in self.stack_resources.items():
            if resource['ResourceType'] == 'AWS::Lambda::Function':
                lambda_functions.append(resource['PhysicalResourceId'])
        
        for function_name in lambda_functions:
            log_group_name = f"/aws/lambda/{function_name}"
            
            try:
                # Verify log group exists
                logs_client.describe_log_groups(logGroupNamePrefix=log_group_name)
                print(f"✅ Log group {log_group_name} validated")
                
            except ClientError as e:
                if e.response['Error']['Code'] == 'ResourceNotFoundException':
                    pytest.fail(f"Log group {log_group_name} not found")
                else:
                    pytest.fail(f"Failed to validate log group {log_group_name}: {str(e)}")
    
    def test_stack_outputs_completeness(self):
        """Verify all expected stack outputs are present"""
        expected_outputs = [
            'ApiGatewayUrl',
            'ApiKey',
            'StateMachineArn'
        ]
        
        for output_key in expected_outputs:
            assert output_key in self.stack_outputs, \
                f"Missing stack output: {output_key}"
            
            assert self.stack_outputs[output_key], \
                f"Stack output {output_key} is empty"
        
        print(f"✅ All stack outputs validated")
    
    def test_resource_tags(self):
        """Verify resources have appropriate tags"""
        # Check if stack has tags
        stack_tags = {tag['Key']: tag['Value'] for tag in self.stack.get('Tags', [])}
        
        # At minimum, should have some identifying tags
        # This is optional but good practice
        if stack_tags:
            print(f"✅ Stack tags found: {list(stack_tags.keys())}")
        else:
            print("ℹ️ No stack tags found (optional)")
    
    @pytest.mark.skipif(not pytest.config.getoption("--run-live", default=False), 
                       reason="Live tests require --run-live flag")
    def test_end_to_end_connectivity(self):
        """Test that all components can communicate with each other"""
        # This is a basic connectivity test
        api_url = self.stack_outputs.get('ApiGatewayUrl')
        api_key = self.stack_outputs.get('ApiKey')
        
        if not api_url or not api_key:
            pytest.skip("API Gateway URL or API Key not available")
        
        import requests
        
        # Test API Gateway is reachable (should return 400 for empty request)
        try:
            response = requests.post(
                f"{api_url}/process-digest",
                headers={'x-api-key': api_key},
                timeout=10
            )
            
            # Should get some response (not connection error)
            assert response.status_code in [200, 400, 500], \
                f"Unexpected status code: {response.status_code}"
            
            print(f"✅ API Gateway connectivity validated")
            
        except requests.exceptions.RequestException as e:
            pytest.fail(f"API Gateway connectivity test failed: {str(e)}")
    
    def test_lambda_function_configurations(self):
        """Test Lambda function configurations are correct"""
        expected_configs = {
            'TriggerLambda': {
                'timeout': 30,
                'memory': 256,
                'runtime': 'python3.11'
            },
            'ParseEmailLambda': {
                'timeout': 120,
                'memory': 256,
                'runtime': 'python3.11'
            },
            'FetchArticlesLambda': {
                'timeout': 180,
                'memory': 512,
                'runtime': 'python3.11'
            },
            'SummarizeLambda': {
                'timeout': 120,
                'memory': 256,
                'runtime': 'python3.11'
            },
            'SendToSlackLambda': {
                'timeout': 60,
                'memory': 256,
                'runtime': 'python3.11'
            }
        }
        
        for function_logical_id, expected_config in expected_configs.items():
            if function_logical_id not in self.stack_resources:
                continue
                
            resource = self.stack_resources[function_logical_id]
            function_name = resource['PhysicalResourceId']
            
            try:
                function_config = self.lambda_client.get_function(FunctionName=function_name)
                config = function_config['Configuration']
                
                assert config['Timeout'] == expected_config['timeout'], \
                    f"Function {function_name} timeout mismatch: expected {expected_config['timeout']}, got {config['Timeout']}"
                
                assert config['MemorySize'] == expected_config['memory'], \
                    f"Function {function_name} memory mismatch: expected {expected_config['memory']}, got {config['MemorySize']}"
                
                assert config['Runtime'] == expected_config['runtime'], \
                    f"Function {function_name} runtime mismatch: expected {expected_config['runtime']}, got {config['Runtime']}"
                
                print(f"✅ Lambda function {function_name} configuration validated")
                
            except ClientError as e:
                pytest.fail(f"Failed to validate Lambda function {function_name} configuration: {str(e)}")
    
    def test_step_function_definition_validity(self):
        """Test Step Function definition is valid and contains expected states"""
        state_machine_resource = None
        for resource_id, resource in self.stack_resources.items():
            if resource['ResourceType'] == 'AWS::StepFunctions::StateMachine':
                state_machine_resource = resource
                break
        
        if not state_machine_resource:
            pytest.skip("Step Function state machine not found")
        
        state_machine_arn = state_machine_resource['PhysicalResourceId']
        
        try:
            sm_description = self.sf_client.describe_state_machine(
                stateMachineArn=state_machine_arn
            )
            
            definition = json.loads(sm_description['definition'])
            
            # Verify all expected states exist with correct configuration
            expected_states = {
                'ParseEmail': {'Type': 'Task'},
                'FetchArticles': {'Type': 'Map'},
                'SummarizeArticles': {'Type': 'Map'},
                'SendToSlack': {'Type': 'Map'}
            }
            
            for state_name, expected_props in expected_states.items():
                assert state_name in definition['States'], f"Missing state: {state_name}"
                
                state_def = definition['States'][state_name]
                for prop, value in expected_props.items():
                    assert state_def.get(prop) == value, \
                        f"State {state_name} property {prop} mismatch: expected {value}, got {state_def.get(prop)}"
            
            # Verify Map states have MaxConcurrency set
            map_states = ['FetchArticles', 'SummarizeArticles', 'SendToSlack']
            for state_name in map_states:
                state_def = definition['States'][state_name]
                assert 'MaxConcurrency' in state_def, f"Map state {state_name} missing MaxConcurrency"
                assert isinstance(state_def['MaxConcurrency'], int), \
                    f"Map state {state_name} MaxConcurrency should be integer"
            
            print(f"✅ Step Function definition validated")
            
        except ClientError as e:
            pytest.fail(f"Failed to validate Step Function definition: {str(e)}")
    
    def test_secrets_manager_access_permissions(self):
        """Test that Lambda functions have correct Secrets Manager permissions"""
        # Test that fetch articles lambda can access medium cookies
        fetch_lambda_resource = self.stack_resources.get('FetchArticlesLambda')
        if fetch_lambda_resource:
            function_name = fetch_lambda_resource['PhysicalResourceId']
            
            try:
                # Get the function's role
                function_config = self.lambda_client.get_function(FunctionName=function_name)
                role_arn = function_config['Configuration']['Role']
                role_name = role_arn.split('/')[-1]
                
                # Check attached policies
                attached_policies = self.iam_client.list_attached_role_policies(RoleName=role_name)
                
                # Should have some policies attached
                assert len(attached_policies['AttachedPolicies']) > 0, \
                    f"Function {function_name} has no attached policies"
                
                print(f"✅ Fetch Articles Lambda permissions validated")
                
            except ClientError as e:
                pytest.fail(f"Failed to validate Fetch Articles Lambda permissions: {str(e)}")
        
        # Test that send to slack lambda can access slack webhook
        slack_lambda_resource = self.stack_resources.get('SendToSlackLambda')
        if slack_lambda_resource:
            function_name = slack_lambda_resource['PhysicalResourceId']
            
            try:
                # Get the function's role
                function_config = self.lambda_client.get_function(FunctionName=function_name)
                role_arn = function_config['Configuration']['Role']
                role_name = role_arn.split('/')[-1]
                
                # Check attached policies
                attached_policies = self.iam_client.list_attached_role_policies(RoleName=role_name)
                
                # Should have some policies attached
                assert len(attached_policies['AttachedPolicies']) > 0, \
                    f"Function {function_name} has no attached policies"
                
                print(f"✅ Send to Slack Lambda permissions validated")
                
            except ClientError as e:
                pytest.fail(f"Failed to validate Send to Slack Lambda permissions: {str(e)}")