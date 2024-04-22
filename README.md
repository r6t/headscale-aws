# "One Button Headscale" deployment on AWS

This project provides an AWS CloudFormation template that deploys Headscale on an EC2 instance in a standalone VPC in your AWS account. This uses IPv6 for the endpoint, and contains two Lambda functions for working with IPv6 properties where CloudFormation does not support them natively.

## Overview

## Components

### EC2 Instance


### Lambda Functions with CloudFormation custom resource triggers

- **IPv6LambdaFunction**: Retrieves and stores the IPv6 CIDR block of the VPC tagged with 'headscale' into an SSM parameter.
- **EndpointAddressLambda**: Extracts the IPv6 address of the newly created EC2 instance and makes it available for further operations.

### VPC and Networking

- A VPC (`HeadscaleVpc`) is configured with both IPv4 and IPv6 CIDR blocks.
- An Internet Gateway and Route Tables ensure connectivity.
- Public Subnet with IPv6 support and association with the Route Table.
- Security Group (`HeadscaleSecurityGroup`) allows SSH traffic from your IP address (`SSHSource` parameter) and HTTPS traffic from ::/0 (any IPv6 address).

### Security


## Deployment

Example AWS CLI command to deploy stack. Modify parameter values:
```aws cloudformation create-stack --stack-name headscale --template-body file://cloudformation.yaml --capabilities CAPABILITY_NAMED_IAM --parameters ParameterKey=PublicKeyParameter,ParameterValue="ssh-ed25519 SSH-PUBLIC-KEY user@computer" ParameterKey=SSHSource,ParameterValue="0000:111:0000:3:0000:0000:0000:0000/64" ParameterKey=HostedZoneId,ParameterValue=XXXXXXXXXXXXXXXXXXXX ParameterKey=HostedZoneDomain,ParameterValue=mycooldomain.com```

## Post-Deployment Configuration


## Security Considerations

- Regularly update the Headscale application and underlying OS for security patches.

## Troubleshooting

- Review CloudFormation Events and Logs if the stack fails to create or update.
- For issues with Headscale itself, refer to the application's documentation and logs for troubleshooting tips.