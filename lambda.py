import json
import boto3
import cfnresponse

def lambda_handler(event, context):
    ec2_client = boto3.client('ec2')
    ssm_client = boto3.client('ssm')
    
    try:
        if event['RequestType'] in ['Create', 'Update']:
            vpcs_response = ec2_client.describe_vpcs(Filters=[{"Name": "tag:Name", "Values": ["headscale"]}])

            if not vpcs_response["Vpcs"]:
                raise ValueError("No VPC found with the name headscale")

            vpc_id = vpcs_response["Vpcs"][0]["VpcId"]
            ipv6_cidr_block = vpcs_response["Vpcs"][0]["Ipv6CidrBlockAssociationSet"][0]["Ipv6CidrBlock"]
            ssm_client.put_parameter(
                    Name="headscaleIPv6CidrBlock",
                    Value=ipv6_cidr_block,
                    Type="String",
                    Overwrite=True
                )
            
            responseData = {'Ipv6CidrBlock': ipv6_cidr_block}
            cfnresponse.send(event, context, cfnresponse.SUCCESS, responseData)
        
        elif event['RequestType'] == 'Delete':
            ssm_client.delete_parameter(Name="headscaleIPv6CidrBlock")
            cfnresponse.send(event, context, cfnresponse.SUCCESS, {}, "CustomResourcePhysicalID")

    except Exception as e:
        responseData = {'Message': str(e)}
        cfnresponse.send(event, context, cfnresponse.FAILED, responseData, "CustomResourcePhysicalID")