from troposphere import Parameter, Ref, Template, Select, GetAZs, Tag, Output, Join, GetAtt, Base64
from troposphere import awslambda, cloudformation, ec2, iam, ssm
from troposphere.route53 import RecordSetType

template = Template()
template.set_description("Headscale IPv6-centric EC2, VPC")

stack_name_parameter = template.add_parameter(Parameter(
    "StackNameParameter",
    Description="Base name for resources. Meant to be headscale, changing can be useful for multiple stacks",
    Type="String",
    Default="headscale",
))

public_key_parameter = template.add_parameter(Parameter(
    "PublicKeyParameter",
    Description="SSH public key for EC2 keypair",
    Type="String",
))

ssh_source_parameter = template.add_parameter(Parameter(
    "SSHSource",
    Description="IPv6 CIDR to allow ssh into EC2 from",
    Type="String",
))

hosted_zone_domain_parameter = template.add_parameter(Parameter(
    "HostedZoneDomain",
    Description="Hosted Zone domain name for Headscale configuration.",
    Type="String",
))

hosted_zone_id_parameter = template.add_parameter(Parameter(
    "HostedZoneId",
    Description="Hosted Zone ID for the Headscale endpoint record.",
    Type="String",
))

ipv6_lambda_execution_role = template.add_resource(iam.Role(
    "LambdaExecutionRole",
    AssumeRolePolicyDocument={
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Principal": {"Service": ["lambda.amazonaws.com"]},
            "Action": ["sts:AssumeRole"]
        }]
    },
    Policies=[iam.Policy(
        PolicyName="root",
        PolicyDocument={
            "Version": "2012-10-17",
            "Statement": [{
                "Effect": "Allow",
                "Action": [
                    "logs:CreateLogGroup",
                    "logs:CreateLogStream",
                    "logs:PutLogEvents",
                    "ec2:DescribeIpv6Pools",
                    "ec2:DescribeVpcs",
                    "ssm:DeleteParameter",
                    "ssm:GetParameter",
                    "ssm:GetParameters",
                    "ssm:PutParameter"
                ],
                "Resource": "*"
            }]
        }
    )]
))

with open("ipv6_cidr_lambda.py", "r") as l:
    lambda_function_code = l.read()

ipv6_function = template.add_resource(awslambda.Function(
    "IPv6LambdaFunction",
    Code=awslambda.Code(
        ZipFile=lambda_function_code,
    ),
    Handler="index.lambda_handler",
    Role=GetAtt(ipv6_lambda_execution_role, "Arn"),
    Runtime="python3.8",
    Timeout=10,
))

ipv6_cidr_ssm = template.add_resource(ssm.Parameter(
    "Ipv6CidrBlockSSMParameter",
    Name="headscaleIPv6CidrBlock",
    Type="String",
    Value="The SSM parameter containing the Headscale VPC IPv6 CIDR block has not been set.",
))

vpc = template.add_resource(ec2.VPC(
    "HeadscaleVpc",
    CidrBlock="10.0.0.0/16",
    EnableDnsSupport=True,
    EnableDnsHostnames=True,
    InstanceTenancy="default",
    Tags=[{
        "Key": "Name",
        "Value": "headscale",
    }],
))

vpcCidrBlock = template.add_resource(ec2.VPCCidrBlock(
    "Headscaleipv6CidrBlock",
    VpcId=Ref(vpc),
    AmazonProvidedIpv6CidrBlock=True,
))

ipv6_custom_resource = template.add_resource(cloudformation.CustomResource(
    "TriggerLambdaCustomResource",
    DependsOn=[ipv6_cidr_ssm],
    ServiceToken=GetAtt(ipv6_function, "Arn"),
))

igw = template.add_resource(ec2.InternetGateway(
    "HeadscaleInternetGateway",
    Tags=[{
        "Key": "Name",
        "Value": "headscale",
    }],
))

gateway_attachment = template.add_resource(ec2.VPCGatewayAttachment(
    "HeadscaleVpcGatewayAttachment",
    VpcId=Ref(vpc),
    InternetGatewayId=Ref(igw),
))

route_table = template.add_resource(ec2.RouteTable(
    "HeadscaleRouteTable",
    VpcId=Ref(vpc),
    Tags=[{
        "Key": "Name",
        "Value": "headscale",
    }],
))

route = template.add_resource(ec2.Route(
    "Route",
    RouteTableId=Ref(route_table),
    DestinationCidrBlock="0.0.0.0/0",
    GatewayId=Ref(igw),
))

ipv6_route = template.add_resource(ec2.Route(
    "Ipv6Route",
    RouteTableId=Ref(route_table),
    DestinationIpv6CidrBlock="::/0",
    GatewayId=Ref(igw),
))

subnet = template.add_resource(ec2.Subnet(
    "HeadscalePublicSubnet",
    VpcId=Ref(vpc),
    CidrBlock="10.0.1.0/24",
    Ipv6CidrBlock=GetAtt(ipv6_custom_resource, "Ipv6CidrBlock"),
    AssignIpv6AddressOnCreation=True,
    MapPublicIpOnLaunch=True,
    AvailabilityZone=Select(
        "0",
        GetAZs("")
    ),
    Tags=[{
        "Key": "Name",
        "Value": "headscale-public",
    }],
))

subnet_route_table_association = template.add_resource(ec2.SubnetRouteTableAssociation(
    "HeadscaleSubnetRouteTableAssociation",
    SubnetId=Ref(subnet),
    RouteTableId=Ref(route_table),
))

ssm_ec2_role = template.add_resource(iam.Role(
    "SSMRoleForEC2",
    AssumeRolePolicyDocument={
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Principal": {"Service": ["ec2.amazonaws.com"]},
            "Action": ["sts:AssumeRole"]
        }]
    },
    ManagedPolicyArns=[
        "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore",
        "arn:aws:iam::aws:policy/AmazonSSMPatchAssociation"
    ],
))

instance_profile = template.add_resource(iam.InstanceProfile(
    "InstanceProfile",
    Roles=[Ref(ssm_ec2_role)],
))

security_group = template.add_resource(ec2.SecurityGroup(
    "HeadscaleSecurityGroup",
    GroupDescription="Headscale EC2 Security Group",
    VpcId=Ref(vpc),
    SecurityGroupIngress=[
        ec2.SecurityGroupRule(
            IpProtocol="tcp",
            FromPort="22",
            ToPort="22",
            CidrIpv6=Ref(ssh_source_parameter),
        ),
        ec2.SecurityGroupRule(
            IpProtocol="tcp",
            FromPort=443,
            ToPort=443,
            CidrIpv6="::/0",
        ),
    ],
    Tags=[{"Key": "Name", "Value": "headscale"}],
))

ec2_keypair = template.add_resource(ec2.KeyPair(
    "EC2Keypair",
    KeyName="HeadscaleSSHPublicKey",
    PublicKeyMaterial=Ref(public_key_parameter)
))

network_interface = ec2.NetworkInterfaceProperty(
    DeviceIndex=0,
    SubnetId=Ref(subnet),
    AssociatePublicIpAddress=True,
    GroupSet=[Ref(security_group)]
)

ec2_instance = template.add_resource(ec2.Instance(
    "EC2Instance",
    ImageId="ami-08116b9957a259459",
    InstanceType="t2.micro",
    IamInstanceProfile=Ref(instance_profile),
    KeyName=Ref(ec2_keypair),
    Tenancy="default",
    NetworkInterfaces=[network_interface],
    EbsOptimized=False,
    SourceDestCheck=True,
    AvailabilityZone=Select(
        "0",
        GetAZs("")
    ),
    UserData=Base64(Join('', [
        "#!/bin/bash\n",
        "apt update\n",
        "apt install neovim -y\n",
        "apt upgrade -y\n",
        "wget --output-document=headscale.deb https://github.com/juanfont/headscale/releases/download/v0.23.0-alpha9/headscale_0.23.0-alpha9_linux_amd64.deb\n",
        "apt install ./headscale.deb -y\n",
        "sed -i 's#server_url: http://127\\.0\\.0\\.1:8080#server_url: https://headscale\\.r6t\\.io:443#' /etc/headscale/config.yaml\n",
        "sed -i 's#listen_addr: 127\\.0\\.0\\.1:8080#listen_addr: 0\\.0\\.0\\.0:443#' /etc/headscale/config.yaml\n",
        "sed -i '/acme_email:/s/.*/acme_email: \"headscale@r6t.io\"/' /etc/headscale/config.yaml\n",
        "sed -i '/tls_letsencrypt_hostname:/s/.*/tls_letsencrypt_hostname: \"headscale.r6t.io\"/' /etc/headscale/config.yaml\n"
        "sed -i 's#tls_letsencrypt_challenge_type: HTTP-01#tls_letsencrypt_challenge_type: TLS-ALPN-01#' /etc/headscale/config.yaml\n",
        "sed -i 's#base_domain: example.com#base_domain: magic.r6t.io#' /etc/headscale/config.yaml\n",
        "sed -i 's#nameservers:\\n - 1\\.1\\.1\\.1#nameservers:\\n - 2001:1608:10:25::1c04:b12f#' /etc/headscale/config.yaml\n",
        "systemctl enable headscale\n",
        "reboot\n",
    ])),
    Tags=[
        Tag("Name", "headscale")
    ]
))

endpoint_address_execution_role = template.add_resource(iam.Role(
    "DNSLambdaExecutionRole",
    AssumeRolePolicyDocument={
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Principal": {"Service": ["lambda.amazonaws.com"]},
            "Action": ["sts:AssumeRole"]
        }]
    },
    Policies=[iam.Policy(
        PolicyName="LambdaEC2DescribeInstancesPolicy",
        PolicyDocument={
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Action": [
                        "logs:CreateLogGroup",
                        "logs:CreateLogStream",
                        "logs:PutLogEvents"
                    ],
                    "Resource": "arn:aws:logs:*:*:*"
                },
                {
                    "Effect": "Allow",
                    "Action": [
                        "ec2:DescribeInstances"
                    ],
                    "Resource": "*"
                }
            ]
        }
)]
))

with open("endpoint_address_lambda.py", "r") as l:
    dns_lambda_function_code = l.read()

endpoint_address_function = template.add_resource(awslambda.Function(
    "DNSLambdaFunction",
    Code=awslambda.Code(
        ZipFile=dns_lambda_function_code,
    ),
    Handler="index.lambda_handler",
    Role=GetAtt(endpoint_address_execution_role, "Arn"),
    DependsOn=[ec2_instance],
    Runtime="python3.8",
    Timeout=10,
))

endpoint_address_lambda_invocation = template.add_resource(cloudformation.CustomResource(
    "DNSLambdaInvocation",
    ServiceToken=GetAtt(endpoint_address_function, "Arn"),
    InstanceId=Ref(ec2_instance),
))

aaaa_record = template.add_resource(RecordSetType(
    "AAAARecord",
    HostedZoneId=Ref(hosted_zone_id_parameter),
    Name=Join("", [Ref(stack_name_parameter), ".", Ref(hosted_zone_domain_parameter)]),
    Type="AAAA",
    TTL="30",
    ResourceRecords=[GetAtt(endpoint_address_lambda_invocation, "Ipv6Address")],
))

with open('cloudformation.yaml', 'w') as file:
    file.write(template.to_yaml())
