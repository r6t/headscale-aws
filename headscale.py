from troposphere import Parameter, Ref, Template
from troposphere.ec2 import VPC, VPCCidrBlock, Subnet, SubnetCidrBlock, Instance, InternetGateway, KeyPair
from troposphere.ec2 import VPCGatewayAttachment, SubnetRouteTableAssociation
from troposphere.ec2 import RouteTable, Route, SecurityGroup, SecurityGroupIngress

template = Template()

public_key_parameter = template.add_parameter(Parameter(
    "PublicKeyParameter",
    Description="SSH public key to be used with EC2 keypair",
    Type="String",
))

vpc = template.add_resource(VPC(
    "HeadscaleVpc",
    CidrBlock="10.0.0.0/16",
    EnableDnsSupport=True,
    EnableDnsHostnames=True,
    InstanceTenancy="default",
))

vpcCidrBlock = template.add_resource(VPCCidrBlock(
    "Headscaleipv6CidrBlock",
    VpcId=Ref(vpc),
    AmazonProvidedIpv6CidrBlock=True,
))

igw = template.add_resource(InternetGateway(
    "HeadscaleInternetGateway",
))

gateway_attachment = template.add_resource(VPCGatewayAttachment(
    "HeadscaleVpcGatewayAttachment",
    VpcId=Ref(vpc),
    InternetGatewayId=Ref(igw),
))

route_table = template.add_resource(RouteTable(
    "HeadscaleRouteTable",
    VpcId=Ref(vpc),
))

route = template.add_resource(Route(
    "Route",
    RouteTableId=Ref(route_table),
    DestinationCidrBlock="0.0.0.0/0",
    GatewayId=Ref(igw),
))

subnet = template.add_resource(Subnet(
    "HeadscalePublicSubnet",
    VpcId=Ref(vpc),
    CidrBlock="10.0.1.0/24",
#    AssignIpv6AddressOnCreation=True,
    MapPublicIpOnLaunch=True,
))

EC2SubnetCidrBlock = template.add_resource(SubnetCidrBlock(
    'EC2SubnetCidrBlock',
#   Ipv6CidrBlock="2600:1f14:2112:1c00::/56",
    SubnetId=Ref(subnet),
))

subnet_route_table_association = template.add_resource(SubnetRouteTableAssociation(
    "MySubnetRouteTableAssociation",
    SubnetId=Ref(subnet),
    RouteTableId=Ref(route_table),
))

security_group = template.add_resource(SecurityGroup(
    "MySecurityGroup",
    GroupDescription="Allow Headscale instance ingress traffic",
    VpcId=Ref(vpc),
))

security_group_ingress = template.add_resource(SecurityGroupIngress(
    "MySecurityGroupIngress",
    GroupId=Ref(security_group),
    IpProtocol="tcp",
    FromPort="22",
    ToPort="22",
    CidrIpv6="2001:558:600a:8b:fca3:bb10:9ff5:6b0a/128",
))

ec2_keypair = template.add_resource(KeyPair(
    "EC2Keypair",
    KeyName="HeadscaleSSHPublicKey",
    PublicKeyMaterial=Ref(public_key_parameter)

))

instance = template.add_resource(Instance(
    "HeadscaleEC2",
    ImageId="ami-08116b9957a259459",
    InstanceType="t2.micro",
    SubnetId=Ref(subnet),
    SecurityGroupIds=[Ref(security_group)],
    KeyName=Ref(ec2_keypair)
))

with open('cloudformation/headscale.yaml', 'w') as file:
    file.write(template.to_yaml())
