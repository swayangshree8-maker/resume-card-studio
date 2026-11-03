# AWS deployment for the Studio control API

This deploys a Lambda HTTPS Function URL and a DynamoDB table. AWS's new Free account plan ends after at most six months or when credits are used; AWS then closes the account and the server stops. Outside that plan, usage beyond AWS free allowances can be billed. Read AWS's current Free Tier FAQ before creating resources. Use the Free account plan, do not upgrade to Paid, and delete the stack if you stop using it.

## 1. Create your AWS account

1. Start at https://aws.amazon.com/free/ and select the Free account plan.
2. Complete identity verification. AWS may request a payment method for verification.
3. Sign in, open CloudShell from the console toolbar, and select the Mumbai region (ap-south-1).

## 2. Deploy the server

Paste these commands into CloudShell:

    git clone --depth 1 https://github.com/swayangshree8-maker/resume-card-studio.git
    cd resume-card-studio/aws
    python3 build_template.py
    aws cloudformation deploy --stack-name ResumeCardStudioControl --template-file cloudformation.generated.json --capabilities CAPABILITY_IAM
    aws cloudformation describe-stacks --stack-name ResumeCardStudioControl --query "Stacks[0].Outputs[?OutputKey=='ApiUrl'].OutputValue | [0]" --output text

The last command prints the API's HTTPS URL. The stack creates one Lambda function, one DynamoDB table with automatic expiry for short-lived session/rate-limit records and 400-day analytics, and a log group with seven-day retention. It sets bounded DynamoDB capacity (10 read/write units), allows browser requests from this site's GitHub Pages origin, limits admin login to five failures per 15 minutes per IP/account, expires sessions after six hours, and rate-limits requests to 300 per minute per IP.

## 3. Set the admin password in AWS

In the AWS Console, open Lambda → Functions → ResumeCardStudioControl-api → Configuration → Environment variables → Edit. Add ADMIN_PASSWORD with a new password of at least 14 characters, then save. If you chose another stack name, use its -api function. Do not put the password in GitHub or send it in chat. The control-panel username is sway.

Open the Function URL and add /api/health; it should show configured: true.

## 4. Connect the site

Send the public Function URL here. The URL is okay to share; do not send AWS passwords, root credentials, or access keys. The website's public API setting and Content Security Policy still need that URL added before the mobile control panel works.

## Delete the server

In CloudShell run:

    aws cloudformation delete-stack --stack-name ResumeCardStudioControl

This deletes the Lambda, DynamoDB table (settings and analytics included), and log group.

## Cost and availability

AWS Free account plan is time-limited; when it ends, AWS closes the account and its resources stop. Outside the Free account plan, AWS services can charge for usage beyond free allowances. Keep the account on Free plan, monitor the Billing/Free Tier dashboard, and delete the CloudFormation stack if you no longer need it. Lambda Function URLs are public HTTPS endpoints; the admin API still requires the configured password and a short-lived bearer session.
