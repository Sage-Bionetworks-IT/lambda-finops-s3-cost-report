import logging
import os
from datetime import datetime

import boto3

from s3_cost_report import ce, ses

LOG = logging.getLogger(__name__)
LOG.setLevel(logging.DEBUG)


iam_client = boto3.client("iam")
sts_client = boto3.client("sts")


def report_periods(today):
    """
    Calculate the time periods for cost explorer.

    This lambda will run at the beginning of the month, looking at the
    previous month and comparing change to the month before that.

    The Start date is inclusive, and the End date is exclusive
    """
    target_period = {}
    compare_period = {}

    # Special-case the two cases where we cross year boundaries
    if today.month == 1:
        # in Jan, look at Dec and Nov of last year
        target_period["Start"] = f"{today.year - 1}-12-01"
        target_period["End"] = f"{today.year}-01-01"

        compare_period["Start"] = f"{today.year - 1}-11-01"
        compare_period["End"] = f"{today.year - 1}-12-01"

    elif today.month == 2:
        # in Feb, look at Jan of this year and Dec of last year
        target_period["Start"] = f"{today.year}-01-01"
        target_period["End"] = f"{today.year}-02-01"

        compare_period["Start"] = f"{today.year - 1}-12-01"
        compare_period["End"] = f"{today.year}-01-01"

    else:
        # no year boundary, look at the previous two months
        target_period["Start"] = f"{today.year}-{(today.month - 1):02}-01"
        target_period["End"] = f"{today.year}-{today.month:02}-01"

        compare_period["Start"] = f"{today.year}-{(today.month - 2):02}-01"
        compare_period["End"] = f"{today.year}-{(today.month - 1):02}-01"

    LOG.info(f"Target month: {target_period}")
    LOG.info(f"Compare month: {compare_period}")

    return target_period, compare_period


def parse_results_by_time(results_by_time, compare=None):
    """
    Transform results returned from Cost Explorer into a useful data structure,
    and optionally calculating change from a previous result.
    """
    data = {}

    minimum = float(os.environ["MINIMUM"])

    for result in results_by_time:
        for group in result["Groups"]:
            amount = float(group["Metrics"][ce.cost_metric]["Amount"])
            if minimum != 0 and amount < minimum:
                LOG.warning(f"Skipping amount ({amount}) less than minimum ({minimum})")
                continue

            if len(group["Keys"]) != 1:
                LOG.error(f"Unexpected grouping: {group['Keys']}")
                continue

            key = group["Keys"][0]
            data[key] = {"total": amount}

            if compare and key in compare:
                _total = data[key]["total"]
                _compare = compare[key]["total"]

                # changes from zero are special cases
                if _compare == 0:
                    if _total == 0:
                        # both are zero, no change
                        pct = 0
                    else:
                        # up from zero, 100% change
                        pct = 1
                else:
                    # calculate percent change
                    pct = (_total / _compare) - 1
            else:
                pct = 1.0

            data[key]["change"] = pct

    return data


def get_service_costs(target_period, compare_period):
    """
    Get service cost information from cost explorer for both time periods
    and generate a multi-level dictionary. The top-level key will be the
    name of the AWS service being summarized, and the subkeys will be the
    literal strings 'total' and 'change'; 'total' will map to a float
    representing total for this service, and 'change' will map to a float
    representing the percent change from the last month.

    Example:
    ```
    ec2:
        total: 12.3
        change: -0.1
    s3:
        total: 32.1
        change: 0.5
    ```
    """

    # First generate data to compare against
    compare_data = ce.get_ce_service_costs(compare_period)
    compare_dict = parse_results_by_time(compare_data["ResultsByTime"])

    # Then generate data our target data, passing in compare data
    target_data = ce.get_ce_service_costs(target_period)
    target_dict = parse_results_by_time(target_data["ResultsByTime"], compare_dict)

    return target_dict


def get_s3_usage_costs(target_period, compare_period):
    """
    Get S3 usage cost information from cost explorer for both time periods
    and generate a multi-level dictionary. The top-level key will be the
    name of the S3 usage type being summarized, and the subkeys will be the
    literal strings 'total' and 'change'; 'total' will map to a float
    representing total for this service, and 'change' will map to a float
    representing the percent change from the last month.

    Example:
    ```
    s3-bytes-out:
        total: 100.0
        change: 0.5
    s3-timed-storage:
        total: 20.0
        change: -0.5
    ```
    """

    compare_ce_data = ce.get_ce_s3_usage_costs(compare_period)
    compare_dict = parse_results_by_time(compare_ce_data["ResultsByTime"])

    target_ce_data = ce.get_ce_s3_usage_costs(target_period)
    target_dict = parse_results_by_time(target_ce_data["ResultsByTime"], compare_dict)

    return target_dict


def lambda_handler(event, context):
    """
    Entry point

    Send monthly email reports to STRIDES admins with monthly totals for
    (1) each AWS service, and (2) each S3 usage type.Include month-over-month
    changes for both service and usage-type totals.
    """

    # Get account name (default to ID if no Alias is set)
    account = sts_client.get_caller_identity()['Account']
    aliases = iam_client.list_account_aliases()['AccountAliases']
    # aliases will have at most one element
    if len(aliases) > 0:
        account = aliases[0]

    # Calculate the reporting periods to send to cost explorer
    now = datetime.now()
    target_month, compare_month = report_periods(now)

    # Build email summary
    per_service = get_service_costs(target_month, compare_month)
    s3_usage = get_s3_usage_costs(target_month, compare_month)

    # Name of the target period for the email subject
    _dt = datetime.fromisoformat(target_month["Start"])
    email_period = _dt.strftime("%B %Y")  # Month Year
    email_subject = f"AWS Monthly Cost Report ({account} {email_period})"

    # Create and send report
    email_html, email_text = ses.build_email_body(per_service, s3_usage)
    ses.send_email(email_subject, email_html, email_text)
