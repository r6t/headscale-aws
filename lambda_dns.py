import boto3
import cfnresponse

def lambda_handler(event, context):
    ec2_client = boto3.client('ec2')
    
    try:
        if event['RequestType'] in ['Create', 'Update']:
            instance_id = event['ResourceProperties']['InstanceId']
            response = ec2_client.describe_instances(InstanceIds=[instance_id])
            
            ipv6_addresses = response['Reservations'][0]['Instances'][0]['NetworkInterfaces'][0]['Ipv6Addresses']
            if not ipv6_addresses:
                raise ValueError("No IPv6 address found for the instance.")
            
            ipv6_address = ipv6_addresses[0]['Ipv6Address']
            responseData = {'Ipv6Address': ipv6_address}
            cfnresponse.send(event, context, cfnresponse.SUCCESS, responseData)
        
        elif event['RequestType'] == 'Delete':
            cfnresponse.send(event, context, cfnresponse.SUCCESS, {}, "CustomResourcePhysicalID")

    except Exception as e:
        responseData = {'Message': str(e)}
        cfnresponse.send(event, context, cfnresponse.FAILED, responseData, "CustomResourcePhysicalID")