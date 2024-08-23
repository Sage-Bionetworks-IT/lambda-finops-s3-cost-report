import logging

import boto3
from botocore.config import Config as BotoConfig

LOG = logging.getLogger(__name__)
LOG.setLevel(logging.DEBUG)

cost_metric = "NetAmortizedCost"

# Use adaptive mode in an attempt to optimize retry back-off
ce_config = BotoConfig(
    retries={
        "mode": "adaptive",  # default mode is legacy
    }
)
ce_client = boto3.client("ce", config=ce_config)


def get_ce_service_costs(period):
    """
    Get cost information grouped by service
    (i.e. service totals)
    """

    response = ce_client.get_cost_and_usage(
        TimePeriod=period,
        Granularity="MONTHLY",
        Metrics=[
            cost_metric,
        ],
        GroupBy=[
            {
                "Type": "DIMENSION",
                "Key": "SERVICE",
            }
        ],
    )

    return response


def get_ce_s3_usage_costs(period):
    """
    Get cost information for S3 grouped by usage type
    (i.e. S3 usage type totals)
    """

    response = ce_client.get_cost_and_usage(
        TimePeriod=period,
        Granularity="MONTHLY",
        Metrics=[
            cost_metric,
        ],
        Filter={
            "Dimensions": {
                "Key": "SERVICE",
                "Values": [
                    "Amazon Simple Storage Service",
                ],
                "MatchOptions": ["EQUALS"],
            }
        },
        GroupBy=[
            {
                "Type": "DIMENSION",
                "Key": "USAGE_TYPE",
            }
        ],
    )

    return response
