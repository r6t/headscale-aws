import boto3
import cfnresponse

def lambda_handler(event, context):
    ec2_client = boto3.client('ec2')
    route53_client = boto3.client('route53')
    ssm_client = boto3.client('ssm')
    
    try:
        if event['RequestType'] in ['Create', 'Update']:
            vpcs_response = ec2_client.describe_vpcs(Filters=[{"Name": "tag:Name", "Values": ["headscale"]}])
            if not vpcs_response["Vpcs"]:
                raise ValueError("No VPC found with the name headscale")

            vpc_id = vpcs_response["Vpcs"][0]["VpcId"]
            ipv6_cidr_block = vpcs_response["Vpcs"][0]["Ipv6CidrBlockAssociationSet"][0]["Ipv6CidrBlock"]
            ssm_client.put_parameter(
                    Name="/config/headscale/ipv6CidrBlock",
                    Value=ipv6_cidr_block,
                    Type="String",
                    Overwrite=True
                )

            hosted_zone_id = event['ResourceProperties']['HostedZoneId']
            hosted_zone = route53_client.get_hosted_zone(Id=hosted_zone_id)
            domain_name = hosted_zone['HostedZone']['Name'].rstrip('.')
            ssm_client.put_parameter(
                    Name="/config/headscale/domainName",
                    Value=domain_name,
                    Type="String",
                    Overwrite=True
                )

            responseData = {'Ipv6CidrBlock': ipv6_cidr_block, 'DomainName': domain_name}
            cfnresponse.send(event, context, cfnresponse.SUCCESS, responseData)
        
        elif event['RequestType'] == 'Delete':
            ssm_client.delete_parameter(Name="/config/headscale/ipv6CidrBlock")
            ssm_client.delete_parameter(Name="/config/headscale/domainName")
            cfnresponse.send(event, context, cfnresponse.SUCCESS, {}, "CustomResourcePhysicalID")

    except Exception as e:
        responseData = {'Message': str(e)}
        cfnresponse.send(event, context, cfnresponse.FAILED, responseData, "CustomResourcePhysicalID")
