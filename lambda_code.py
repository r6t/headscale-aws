import requests
import boto3
import json


def send_response(
    event,
    context,
    response_status,
    response_data,
    physical_resource_id=None,
    no_echo=False,
    reason=None,
):
    response_url = event["ResponseURL"]

    response_body = json.dumps(
        {
            "Status": response_status,
            "Reason": reason
            or f"See the details in CloudWatch Log Stream: {context.log_stream_name}",
            "PhysicalResourceId": physical_resource_id or context.log_stream_name,
            "StackId": event["StackId"],
            "RequestId": event["RequestId"],
            "LogicalResourceId": event["LogicalResourceId"],
            "NoEcho": no_echo,
            "Data": response_data,
        }
    )

    headers = {"content-type": "", "content-length": str(len(response_body))}

    try:
        response = requests.put(response_url, data=response_body, headers=headers)
        return response
    except Exception as e:
        raise Exception(f"Failed to send CloudFormation response with error {e}")


def lambda_handler(event, context):
    ec2_client = boto3.client("ec2")
    ssm_client = boto3.client("ssm")

    try:
        # Finding the VPC ID by VPC Name (assuming the name is unique)
        vpcs_response = ec2_client.describe_vpcs(
            Filters=[{"Name": "tag:Name", "Values": ["headscale"]}]
        )

        if not vpcs_response["Vpcs"]:
            raise ValueError("No VPC found with the name headscale")

        vpc_id = vpcs_response["Vpcs"][0]["VpcId"]
        ipv6_cidr_block = vpcs_response["Vpcs"][0]["Ipv6CidrBlockAssociationSet"][0][
            "Ipv6CidrBlock"
        ]

        # Store the IPv6 CIDR block in SSM
        ssm_client.put_parameter(
            Name="headscaleIPv6CidrBlock",
            Value=ipv6_cidr_block,
            Type="String",
            Overwrite=True,
        )

        send_response(
            event,
            context,
            "SUCCESS",
            {
                "Message": f"Successfully updated SSM Parameter with IPv6 CIDR Block for VPC {vpc_id}"
            },
            physical_resource_id=vpc_id,
        )

    except Exception as e:
        send_response(event, context, "FAILED", {"Message": str(e)}, reason=str(e))