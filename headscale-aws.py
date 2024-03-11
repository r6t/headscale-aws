from troposphere import Ref, Template
from troposphere.ec2 import VPC, Subnet, Instance, InternetGateway
from troposphere.ec2 import VPCGatewayAttachment, SubnetRouteTableAssociation
from troposphere.ec2 import RouteTable, Route, SecurityGroup, SecurityGroupIngress
template = Template()

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

# Add a security group
security_group = template.add_resource(SecurityGroup(
    "MySecurityGroup",
    GroupDescription="Allow SSH from specific IPv6 address",
    VpcId=Ref(vpc),
))

# Add a security group ingress rule
security_group_ingress = template.add_resource(SecurityGroupIngress(
    "MySecurityGroupIngress",
    GroupId=Ref(security_group),
    IpProtocol="tcp",
    FromPort="22",
    ToPort="22",
    CidrIpv6="2601:602:9300:9::1c55/128",  # Replace with your IPv6 address
))

instance = template.add_resource(Instance(
    "MyInstance",
    ImageId="ami-0abcdef1234567890",  # replace with your AMI ID
    InstanceType="t2.micro",
    SubnetId=Ref(subnet),
    SecurityGroupIds=[Ref(security_group)],  # Add the security group to the instance
))

with open('cloudformation/headscale-aws.json', 'w') as file:
    file.write(template.to_json())
