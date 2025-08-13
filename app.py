#!/usr/bin/env python3
import os
import aws_cdk as cdk
from medium_digest_summarizer.medium_digest_summarizer_stack import MediumDigestSummarizerStack

app = cdk.App()
MediumDigestSummarizerStack(app, "MediumDigestSummarizerStack",
    # Deploy to us-east-1 region as specified in requirements
    env=cdk.Environment(
        account=os.getenv('CDK_DEFAULT_ACCOUNT'), 
        region='us-east-1'
    )
    )

app.synth()