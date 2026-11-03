"""Generate the AWS CloudFormation template with inline Lambda source."""
import json
from pathlib import Path

root = Path(__file__).resolve().parent
handler = (root / "handler.py").read_text(encoding="utf-8")
template = {
    "AWSTemplateFormatVersion": "2010-09-09",
    "Description": "Studio control API: Lambda Function URL and DynamoDB",
    "Parameters": {
        "AdminUsername": {
            "Type": "String", "Default": "sway", "MinLength": "1", "MaxLength": "80",
            "Description": "Username for the private control panel",
        }
    },
    "Resources": {
        "ControlData": {
            "Type": "AWS::DynamoDB::Table",
            "Properties": {
                "TableName": {"Fn::Sub": "$" + "{AWS::StackName}-data"},
                "AttributeDefinitions": [
                    {"AttributeName": "pk", "AttributeType": "S"},
                    {"AttributeName": "sk", "AttributeType": "S"},
                ],
                "KeySchema": [
                    {"AttributeName": "pk", "KeyType": "HASH"},
                    {"AttributeName": "sk", "KeyType": "RANGE"},
                ],
                "BillingMode": "PROVISIONED",
                "ProvisionedThroughput": {"ReadCapacityUnits": 10, "WriteCapacityUnits": 10},
                "TimeToLiveSpecification": {"AttributeName": "expires_at", "Enabled": True},
            },
        },
        "LambdaRole": {
            "Type": "AWS::IAM::Role",
            "Properties": {
                "AssumeRolePolicyDocument": {
                    "Version": "2012-10-17",
                    "Statement": [{
                        "Effect": "Allow", "Principal": {"Service": "lambda.amazonaws.com"},
                        "Action": "sts:AssumeRole",
                    }],
                },
                "ManagedPolicyArns": [
                    "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
                ],
                "Policies": [{
                    "PolicyName": "ControlDataOnly",
                    "PolicyDocument": {
                        "Version": "2012-10-17",
                        "Statement": [{
                            "Effect": "Allow",
                            "Action": [
                                "dynamodb:GetItem", "dynamodb:PutItem",
                                "dynamodb:UpdateItem", "dynamodb:Query",
                            ],
                            "Resource": {"Fn::GetAtt": ["ControlData", "Arn"]},
                        }],
                    },
                }],
            },
        },
        "ControlLogGroup": {
            "Type": "AWS::Logs::LogGroup",
            "Properties": {
                "LogGroupName": {"Fn::Sub": "/aws/lambda/$" + "{AWS::StackName}-api"},
                "RetentionInDays": 7,
            },
        },
        "ControlApi": {
            "Type": "AWS::Lambda::Function",
            "DependsOn": ["ControlLogGroup"],
            "Properties": {
                "FunctionName": {"Fn::Sub": "$" + "{AWS::StackName}-api"},
                "Runtime": "python3.12",
                "Handler": "index.lambda_handler",
                "Role": {"Fn::GetAtt": ["LambdaRole", "Arn"]},
                "MemorySize": 256,
                "Timeout": 30,
                "Environment": {
                    "Variables": {
                        "TABLE_NAME": {"Ref": "ControlData"},
                        "ADMIN_USERNAME": {"Ref": "AdminUsername"},
                    }
                },
                "Code": {"ZipFile": handler},
            },
        },
        "ControlApiUrl": {
            "Type": "AWS::Lambda::Url",
            "Properties": {
                "TargetFunctionArn": {"Fn::GetAtt": ["ControlApi", "Arn"]},
                "AuthType": "NONE",
                "Cors": {
                    "AllowOrigins": ["https://swayangshree8-maker.github.io"],
                    "AllowMethods": ["GET", "POST"],
                    "AllowHeaders": ["Authorization", "Content-Type"],
                    "MaxAge": 600,
                },
            },
        },
        "PublicUrlPermission": {
            "Type": "AWS::Lambda::Permission",
            "Properties": {
                "FunctionName": {"Ref": "ControlApi"},
                "Action": "lambda:InvokeFunctionUrl",
                "Principal": "*",
                "FunctionUrlAuthType": "NONE",
            },
        },
        "UrlInvokePermission": {
            "Type": "AWS::Lambda::Permission",
            "Properties": {
                "FunctionName": {"Ref": "ControlApi"},
                "Action": "lambda:InvokeFunction",
                "Principal": "*",
                "InvokedViaFunctionUrl": True,
            },
        },
    },
    "Outputs": {
        "ApiUrl": {
            "Description": "Public HTTPS API endpoint",
            "Value": {"Fn::GetAtt": ["ControlApiUrl", "FunctionUrl"]},
        },
        "FunctionName": {"Value": {"Ref": "ControlApi"}},
        "TableName": {"Value": {"Ref": "ControlData"}},
    },
}
output = root / "cloudformation.generated.json"
output.write_text(json.dumps(template, indent=2) + "\n", encoding="utf-8")
print(f"Created {output.name} ({output.stat().st_size} bytes)")
