from troposphere import Parameter, Ref, Template, Select, GetAZs, Tag, Output, Join, GetAtt, Base64, Sub
from troposphere import awslambda, cloudformation, ec2, iam, ssm
from troposphere.route53 import RecordSetType

template = Template()
template.set_description("Headscale IPv6-centric EC2 stack")

stack_name_parameter = template.add_parameter(Parameter(
    "StackName",
    Description="Base name for resources. Meant to be headscale, changing can be useful for multiple stacks",
    Type="String",
    Default="headscale",
))

headscale_release_parameter = template.add_parameter(Parameter(
    "HeadscaleRelease",
    Description="Headscale release version to use: https://github.com/juanfont/headscale/releases",
    Type="String",
    Default="0.23.0-alpha9",
))

hosted_zone_id_parameter = template.add_parameter(Parameter(
    "HostedZoneId",
    Description="Hosted Zone ID for the Headscale endpoint record.",
    Type="String",
))

nextdns_id_parameter = template.add_parameter(Parameter(
    "NextDnsId",
    Description="NextDNS account to be used with Headscale",
    Type="String",
))

magicdns_parameter = template.add_parameter(Parameter(
    "MagicDnsName",
    Description="MagicDNS/Headscale internal network domain name",
    Type="String",
))

ipv6_cidr_ssm = template.add_resource(ssm.Parameter(
    "Ipv6CidrBlockSSM",
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
        "Value": Ref(stack_name_parameter),
    }],
))

vpcCidrBlock = template.add_resource(ec2.VPCCidrBlock(
    "Headscaleipv6CidrBlock",
    VpcId=Ref(vpc),
    AmazonProvidedIpv6CidrBlock=True,
))

igw = template.add_resource(ec2.InternetGateway(
    "HeadscaleInternetGateway",
    Tags=[{
        "Key": "Name",
        "Value": Ref(stack_name_parameter)
    }],
))

gateway_attachment = template.add_resource(ec2.VPCGatewayAttachment(
    "HeadscaleVpcGatewayAttachment",
    DependsOn=[vpcCidrBlock],
    VpcId=Ref(vpc),
    InternetGatewayId=Ref(igw),
))

route_table = template.add_resource(ec2.RouteTable(
    "HeadscaleRouteTable",
    VpcId=Ref(vpc),
    Tags=[{
        "Key": "Name",
        "Value": Ref(stack_name_parameter)
    }],
))

route = template.add_resource(ec2.Route(
    "Route",
    DependsOn=[gateway_attachment],
    RouteTableId=Ref(route_table),
    DestinationCidrBlock="0.0.0.0/0",
    GatewayId=Ref(igw),
))

ipv6_route = template.add_resource(ec2.Route(
    "Ipv6Route",
    DependsOn=[route],
    RouteTableId=Ref(route_table),
    DestinationIpv6CidrBlock="::/0",
    GatewayId=Ref(igw),
))

ssm_lambda_execution_role = template.add_resource(iam.Role(
    "SSMLambdaExecutionRole",
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
                    "ssm:PutParameter",
                    "route53:GetHostedZone"
                ],
                "Resource": "*"
            }]
        }
    )]
))

with open("lambda_ssm.py", "r") as l:
    ssm_lambda_function_code = l.read()

ssm_function = template.add_resource(awslambda.Function(
    "SSMLambdaFunction",
    Code=awslambda.Code(
        ZipFile=ssm_lambda_function_code,
    ),
    DependsOn=[ipv6_route],
    Handler="index.lambda_handler",
    Role=GetAtt(ssm_lambda_execution_role, "Arn"),
    Runtime="python3.8",
    Timeout=10,
))

ssm_lambda_invocation = template.add_resource(cloudformation.CustomResource(
    "TriggerSSMLambdaCustomResource",
    DependsOn=[ipv6_cidr_ssm],
    ServiceToken=GetAtt(ssm_function, "Arn"),
    HostedZoneId=Ref(hosted_zone_id_parameter),
))

subnet = template.add_resource(ec2.Subnet(
    "HeadscalePublicSubnet",
    VpcId=Ref(vpc),
    CidrBlock="10.0.1.0/24",
    Ipv6CidrBlock=GetAtt(ssm_lambda_invocation, "Ipv6CidrBlock"),
    AssignIpv6AddressOnCreation=True,
    MapPublicIpOnLaunch=True,
    AvailabilityZone=Select(
        "0",
        GetAZs("")
    ),
    Tags=[{
        "Key": "Name",
        "Value": Ref(stack_name_parameter)
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
            FromPort=443,
            ToPort=443,
            CidrIpv6="::/0",
        ),
    ],
    Tags=[{"Key": "Name", "Value": Ref(stack_name_parameter)}],
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
        "export DEBIAN_FRONTEND=noninteractive\n",
        "apt update\n",
        "apt install neovim python3-pip -y\n",
        "pip3 install yq\n",
        "apt upgrade -y\n",
        "wget --output-document=headscale.deb https://github.com/juanfont/headscale/releases/download/v",
        Ref(headscale_release_parameter),
        "/headscale_",
        Ref(headscale_release_parameter),
        "_linux_amd64.deb\n",
        "apt install ./headscale.deb -y\n",
        "sed -i 's#server_url: http://127.0.0.1:8080#server_url: https://",
        Ref(stack_name_parameter),
        ".",
        GetAtt(ssm_lambda_invocation, "DomainName"),
        "#' /etc/headscale/config.yaml\n",
        "sed -i 's#listen_addr: 127.0.0.1:8080#listen_addr: 0.0.0.0:443#' /etc/headscale/config.yaml\n",
        "sed -i '/acme_email:/s/.*/acme_email: \"headscale@",
        GetAtt(ssm_lambda_invocation, "DomainName"),
        "\"/' /etc/headscale/config.yaml\n",
        "sed -i '/tls_letsencrypt_hostname:/s/.*/tls_letsencrypt_hostname: \"",
        Ref(stack_name_parameter),
        ".",
        GetAtt(ssm_lambda_invocation, "DomainName"),
        "\"/' /etc/headscale/config.yaml\n",
        "sed -i 's#tls_letsencrypt_challenge_type: HTTP-01#tls_letsencrypt_challenge_type: TLS-ALPN-01#' /etc/headscale/config.yaml\n",
        "sed -i 's#base_domain: example.com#base_domain: ",
        Ref(magicdns_parameter),
        "#' /etc/headscale/config.yaml\n",
        "yq eval '.nameservers[0] = \"https://dns.nextdns.io/",
        Ref(nextdns_id_parameter),
        "\"' -i /etc/headscale/config.yaml\n",
        "systemctl enable headscale\n",
        "reboot\n",
    ])),
    Tags=[
        Tag("Name", Ref(stack_name_parameter))
    ]
))

dns_execution_role = template.add_resource(iam.Role(
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
                        "ec2:DescribeInstances",
                        "route53:ListHostedZones",
                        "route53:GetHostedZone"
                    ],
                    "Resource": "*"
                }
            ]
        }
)]
))

with open("lambda_dns.py", "r") as l:
    dns_lambda_function_code = l.read()

dns_function = template.add_resource(awslambda.Function(
    "DNSLambdaFunction",
    Code=awslambda.Code(
        ZipFile=dns_lambda_function_code,
    ),
    Handler="index.lambda_handler",
    Role=GetAtt(dns_execution_role, "Arn"),
    DependsOn=[ec2_instance],
    Runtime="python3.8",
    Timeout=10,
))

dns_lambda_invocation = template.add_resource(cloudformation.CustomResource(
    "DNSLambdaInvocation",
    ServiceToken=GetAtt(dns_function, "Arn"),
    InstanceId=Ref(ec2_instance),
))

aaaa_record = template.add_resource(RecordSetType(
    "AAAARecord",
    HostedZoneId=Ref(hosted_zone_id_parameter),
    Name=Join("", [Ref(stack_name_parameter), ".", GetAtt(ssm_lambda_invocation, "DomainName")]),
    Type="AAAA",
    TTL="300",
    ResourceRecords=[GetAtt(dns_lambda_invocation, "Ipv6Address")],
))

template.add_output(Output(
    "HeadscaleApplicationURL",
    Description="Headscale application URL",
    Value=Join("", [
        "https://",
        Ref(stack_name_parameter),
        ".",
        GetAtt(ssm_lambda_invocation, "DomainName")
    ])
))

with open('cloudformation.yaml', 'w') as file:
    file.write(template.to_yaml())
