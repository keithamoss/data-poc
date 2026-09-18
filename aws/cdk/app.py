#!/usr/bin/env python3
"""CDK app entry point for the event-driven MVP (plans/running-thoughts.md
#5 Thread B / docs/aws-event-driven-mvp-design.md). See that design doc for
the full architecture - this file just wires the one stack up for `cdk
synth`/`cdk deploy`, neither of which has run in this sandbox (no AWS CLI,
no CDK CLI, no real credentials - see data_pipeline_stack.py's own module
docstring)."""
from __future__ import annotations

import aws_cdk as cdk

from data_pipeline_stack import DataPipelineStack

app = cdk.App()
DataPipelineStack(app, "DataPipelineStack")
app.synth()
