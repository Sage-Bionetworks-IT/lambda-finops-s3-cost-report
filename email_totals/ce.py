import logging
from datetime import datetime, timedelta

import boto3
from botocore.config import Config as BotoConfig


LOG = logging.getLogger(__name__)
LOG.setLevel(logging.DEBUG)

cost_metric = 'NetAmortizedCost'

# Use adaptive mode in an attempt to optimize retry back-off
ce_config = BotoConfig(
    retries = {
        'mode': 'adaptive',  # default mode is legacy
    }
)
ce_client = boto3.client('ce', config=ce_config)

# get_cost_and_usage_with_resources() can only look back at most 14 days,
# but we only need current resources missing tags, so hard-code the period
# to be yesterday; store it in a global variable to avoid recalculating it
# on every call to get_ce_missing_tag_for_email()
today = datetime.now()
yesterday = {}
yesterday['Start'] = (today - timedelta(days=1)).strftime('%Y-%m-%d')
yesterday['End'] = today.strftime('%Y-%m-%d')


def get_ce_email_costs(period):
    """
    Get cost information grouped by owner email then account
    (i.e. email totals for each account)
    """

    response = ce_client.get_cost_and_usage(
        TimePeriod=period,
        Granularity='MONTHLY',
        Metrics=[
            cost_metric,
        ],
        GroupBy=[{
            'Type': 'COST_CATEGORY',
            'Key': 'Owner Email',
        }, {
            'Type': 'DIMENSION',
            'Key': 'LINKED_ACCOUNT',
        }],
    )

    return response


def get_ce_account_costs(period):
    """
    Get cost information grouped by account (i.e. account totals)
    """

    response = ce_client.get_cost_and_usage(
        TimePeriod=period,
        Granularity='MONTHLY',
        Metrics=[
            cost_metric,
        ],
        GroupBy=[{
            'Type': 'DIMENSION',
            'Key': 'LINKED_ACCOUNT',
        }],
    )

    return response


def get_ce_invalid_tag_for_email(email):
    """
    Get cost category resource information for a given owner email and
    grouped by account, filtered for resources where the CostCenterOther
    is set and CostCenter is not 'Other / 000001'.
    """

    response = ce_client.get_cost_and_usage_with_resources(
        TimePeriod=yesterday,
        Granularity='MONTHLY',
        Metrics=[
            cost_metric,
        ],
        Filter={
            'And': [{
                'CostCategories': {
                    'Key': 'Owner Email',
                    'Values': [email, ],
                    'MatchOptions': ['EQUALS', ],
                }
            }, {
                'Not': {
                    'Tags': {
                        'Key': 'CostCenter',
                        'Values': ['Other / 000001', ],
                        'MatchOptions': ['EQUALS', ],
                    }
                }
            }, {
                'Not': {
                    'Tags': {
                        'Key': 'CostCenterOther',
                        'MatchOptions': ['ABSENT', ],
                    }
                }
            }
        ]},
        GroupBy=[{
            'Type': 'DIMENSION',
            'Key': 'LINKED_ACCOUNT',
        }, {
            'Type': 'DIMENSION',
            'Key': 'RESOURCE_ID',
        }],
    )

    return response


def get_ce_missing_tag_for_email(email):
    """
    Get cost category resource information for a given owner email and
    grouped by account, filtered for resources where the CostCenter tag
    is 'Other / 000001' but the CostCenterOther tag is absent.
    """

    response = ce_client.get_cost_and_usage_with_resources(
        TimePeriod=yesterday,
        Granularity='MONTHLY',
        Metrics=[
            cost_metric,
        ],
        Filter={"And": [
            {'CostCategories': {
                'Key': 'Owner Email',
                'Values': [email, ],
                'MatchOptions': ['EQUALS', ],
            }
            }, {'Tags': {
                'Key': 'CostCenter',
                'Values': ['Other / 000001', ],
                'MatchOptions': ['EQUALS', ],
            }
            }, {'Tags': {
                'Key': 'CostCenterOther',
                'MatchOptions': ['ABSENT', ],
            }
            }
        ]},
        GroupBy=[{
            'Type': 'DIMENSION',
            'Key': 'LINKED_ACCOUNT',
        }, {
            'Type': 'DIMENSION',
            'Key': 'RESOURCE_ID',
        }],
    )

    return response
