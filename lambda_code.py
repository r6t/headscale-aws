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