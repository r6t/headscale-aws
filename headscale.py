from troposphere import Parameter, Ref, Template
from troposphere.ec2 import VPC, Subnet, Instance, InternetGateway
from troposphere.ec2 import VPCGatewayAttachment, SubnetRouteTableAssociation
from troposphere.ec2 import RouteTable, Route, SecurityGroup, SecurityGroupIngress, KeyPair
import troposphere.ssm

template = Template()

# Define the parameter for KeyPair's public key material
public_key_parameter = template.add_parameter(Parameter(
    "PublicKeyMaterial",
    Description="Public Key Material for EC2 KeyPair",
    Type="String",
))

vpc = template.add_resource(VPC(
    "HeadscaleVpc",
    CidrBlock="2001:db8::/32",  # IPv6 CIDR block
    EnableDnsSupport="true",
    EnableDnsHostnames="true",
    InstanceTenancy="default",
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
    DestinationCidrBlock="::/0",  # IPv6 for all addresses
    GatewayId=Ref(igw),
))

subnet = template.add_resource(Subnet(
    "MySubnet",
    VpcId=Ref(vpc),
    CidrBlock="2001:db8::/64",  # IPv6 CIDR block
    MapPublicIpOnLaunch="true",
))

subnet_route_table_association = template.add_resource(SubnetRouteTableAssociation(
    "MySubnetRouteTableAssociation",
    SubnetId=Ref(subnet),
    RouteTableId=Ref(route_table),
))

security_group = template.add_resource(SecurityGroup(
    "MySecurityGroup",
    GroupDescription="Allow SSH from specific IPv6 address",
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

key_pair = template.add_resource(KeyPair(
    "HeadscaleEC2Keypair",
    KeyName="HeadscaleEC2Keypair",
    PublicKeyMaterial=Ref(public_key_parameter),
))

instance = template.add_resource(Instance(
    "HeadscaleEC2",
    ImageId="ami-08116b9957a259459",
    InstanceType="t2.micro",
    SubnetId=Ref(subnet),
    SecurityGroupIds=[Ref(security_group)],
))

with open('cloudformation/headscale-aws.json', 'w') as file:
    file.write(template.to_json())
