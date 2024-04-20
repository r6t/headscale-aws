from troposphere import Parameter, Ref, Template, Select, GetAZs, Tag, Output, Join, GetAtt
from troposphere import awslambda, cloudformation, ec2, iam, ssm

template = Template()

public_key_parameter = template.add_parameter(Parameter(
    "PublicKeyParameter",
    Description="SSH public key to be used with EC2 keypair",
    Type="String",
))

ssh_source_parameter = template.add_parameter(Parameter(
    "SSHSource",
    Description="IPv4 Address to allow ssh in from. e.g., x.x.x.x/32", # move to ipv6 once ipv6 support is there
    Type="String",
))

hosted_zone_id_parameter = template.add_parameter(Parameter(
    "HostedZoneId",
    Description="Hosted Zone ID to use for the Headscale endpoint.",
    Type="String",
))

lambda_execution_role = template.add_resource(iam.Role(
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
                    "ssm:PutParameter"
                ],
                "Resource": "*"
            }]
        }
    )]
))

ipv6_lookup_function = template.add_resource(awslambda.Function(
    "IPv6LookupLambdaFunction",
    Code=awslambda.Code(
        ZipFile=("""
import json
import boto3
import cfnresponse

def lambda_handler(event, context):
    ec2_client = boto3.client('ec2')
    ssm_client = boto3.client('ssm')

    # Initialize responseData
    response_data = {}

    try:
        # Finding the VPC ID by VPC Name (assuming the name is unique)
        vpcs_response = ec2_client.describe_vpcs(Filters=[{"Name": "tag:Name", "Values": ["headscale"]}])

        if not vpcs_response["Vpcs"]:
            raise ValueError("No VPC found with the name headscale")

        vpc_id = vpcs_response["Vpcs"][0]["VpcId"]
        ipv6_cidr_block = vpcs_response["Vpcs"][0]["Ipv6CidrBlockAssociationSet"][0]["Ipv6CidrBlock"]

        # Store the IPv6 CIDR block in SSM
        ssm_client.put_parameter(
            Name="headscaleIPv6CidrBlock",
            Value=ipv6_cidr_block,
            Type="String",
            Overwrite=True
        )

        response_data['IPv6CidrBlock'] = ipv6_cidr_block
        cfnresponse.send(event, context, cfnresponse.SUCCESS, response_data, physicalResourceId=vpc_id)

    except Exception as e:
        response_data['Message'] = str(e)
        cfnresponse.send(event, context, cfnresponse.FAILED, response_data, reason=str(e))
"""),
    ),
    Handler="index.lambda_handler",
    Role=GetAtt(lambda_execution_role, "Arn"),
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

custom_resource = template.add_resource(cloudformation.CustomResource(
    "TriggerLambdaCustomResource",
    ServiceToken=GetAtt(ipv6_lookup_function, "Arn"),
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

subnet = template.add_resource(ec2.Subnet(
    "HeadscalePublicSubnet",
    VpcId=Ref(vpc),
    CidrBlock="10.0.1.0/24",
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

security_group = template.add_resource(ec2.SecurityGroup(
    "HeadscaleSecurityGroup",
    GroupDescription="Headscale EC2 Security Group",
    VpcId=Ref(vpc),
    SecurityGroupIngress=[
        ec2.SecurityGroupRule(
            IpProtocol="tcp",
            FromPort="22",
            ToPort="22",
            CidrIp=Ref(ssh_source_parameter),
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
    KeyName=Ref(ec2_keypair),
    Tenancy="default",
    NetworkInterfaces=[network_interface],
    EbsOptimized=False,
    SourceDestCheck=True,
    AvailabilityZone=Select(
        "0",
        GetAZs("")
    ),
    Tags=[
        Tag("Name", "headscale")
    ]
))

with open('cloudformation/headscale.yaml', 'w') as file:
    file.write(template.to_yaml())
