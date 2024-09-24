import logging
import os

import boto3
from botocore.config import Config as BotoConfig
from botocore.exceptions import ClientError

LOG = logging.getLogger(__name__)
LOG.setLevel(logging.DEBUG)

# Use standard mode in order to retry on RequestLimitExceeded
# and increase the default number of retries to 10
ses_config = BotoConfig(
    retries={
        "mode": "standard",  # default mode is legacy
        "max_attempts": 10,  # default for standard mode is 3
    }
)
ses_client = boto3.client("ses", config=ses_config)


def _table_row_style(i):
    """
    Alternating table row background colors.
    """
    if i % 2 == 0:
        return "style='background-color: WhiteSmoke;'"
    else:
        return ""


def build_paragraph(text, html=False):
    """
    Format a text block as a paragraph.
    """
    output = ""

    if html:
        # Put the paragraph in an invisible table to wrap long lines;
        # give the table a single row with two cells, put the text in
        # the first cell and let the second cell fill any extra space
        output += (
            "<table border='0' width='100%' "
            "style='border-collapse: collapse;'><tr>"
            f"<td width='600'>{text}</td><td></td>"
            "</tr></table>"
        )
    else:
        # Just add a newline
        output += text + "\n"

    return output


def build_service_table(services, html=False):
    """
    Build a table from a dictionary of service totals.

    Example input block:
    ```
    ec2:
        total: 10.0
    s3:
        total: 20.0
        change: 0.5
    ```
    """

    output = ""

    # Table header
    if html:
        output += (
            "<table border='1' padding='10' width='600' "
            "style='border-collapse: collapse; text-align: center;'>"
            "<tr style='background-color: LightSteelBlue'>"
            "<th>AWS Service</th>"
            f"<th>Total</th><th>Month-over-Month Change</th></tr>"
        )
        row_i = 0  # row index for coloring table rows
    else:
        output += (
            "\t".join(["AWS Service", "Total", "Month-over-Month Change"])
            + "\n"
        )

    # Table rows
    for service in services:
        # Round dollar total to 2 decimal places
        total = f"${services[service]['total']:.2f}"

        change = ""
        if "change" in services[service]:
            # Convert to a percentage
            change = f"{services[service]['change']:.2%}"

        if html:
            _td = f"<td>{service}</td>" f"<td>{total}</td><td>{change}</td>"

            _style = _table_row_style(row_i)
            output += f"<tr {_style}>{_td}</tr>"
            row_i += 1

        else:
            _td = [service, total, change]
            output += "\t".join(_td) + "\n"

    # Table end
    if html:
        output += "</table><br/>"

    return output


def build_usage_table(usages, html=False):
    """
    Build a table from a dictionary of S3 usage costs

    Example input block:
    ```
    s3-bytes-out:
        total: 10.0
    s3-timed-storage:
        total: 20.0
        change: 0.5
    ```
    """

    output = ""
    total = "Total"

    # Table header
    if html:
        output += (
            "<table border='1' padding='10' width='600' "
            "style='border-collapse: collapse; text-align: center;'>"
            "<tr style='background-color: LightSteelBlue'>"
            "<th>S3 Usage Type</th>"
            f"<th>Total</th><th>Month-over-Month Change</th></tr>"
        )
        row_i = 0  # row index for coloring table rows
    else:
        output += (
            "\t".join(["S3 Usage Type", "Total", "Month-over-Month Change"])
            + "\n"
        )

    # Table rows
    for usage_type in usages:
        # Round dollar total to 2 decimal places
        total = f"${usages[usage_type]['total']:.2f}"

        change = ""
        if "change" in usages[usage_type]:
            # Convert to a percentage
            change = f"{usages[usage_type]['change']:.2%}"

        if html:
            _td = (
                f"<td>{usage_type}</td>"
                f"<td>{total}</td><td>{change}</td>"
            )

            _style = _table_row_style(row_i)
            output += f"<tr {_style}>{_td}</tr>"
            row_i += 1

        else:
            _td = [usage_type, total, change]
            output += "\t".join(_td) + "\n"

    # Table end
    if html:
        output += "</table><br/>"

    return output


def build_email_body(service_data, s3_usage_data):
    """
    Compose the email bodies (both a plain-text and HTML version), with
    a table for service costs, and a table for S3 usage type costs.
    """

    # Ignore totals under this amount
    minimum = float(os.environ["MINIMUM"])

    service_prose = "\nBreak-down of total monthly costs by service:"
    s3_usage_prose = "\nBreak-down of monthly S3 costs by usage type:"
    no_data_prose = "\nNo matching data found "

    title = "AWS Monthly Cost Summary"
    html_body = f"<h3>{title}</h3>"
    text_body = f"{title}\n"

    if service_data:
        html_body += build_paragraph(service_prose, True)
        text_body += build_paragraph(service_prose, False)

        html_body += build_service_table(service_data, True)
        text_body += build_service_table(service_data, False)
    else:
        no_service_data = f"{no_data_prose} for service totals"
        html_body += build_paragraph(no_service_data, True)
        text_body += build_paragraph(service_prose, False)

    if s3_usage_data:
        html_body += build_paragraph(s3_usage_prose, True)
        text_body += build_paragraph(s3_usage_prose, False)

        html_body += build_usage_table(s3_usage_data, True)
        text_body += build_usage_table(s3_usage_data, False)
    else:
        no_s3_usage_data = f"{no_data_prose} for S3 usage totals"
        html_body += build_paragraph(no_s3_usage_data, True)
        text_body += build_paragraph(service_prose, False)

    LOG.debug(html_body)
    LOG.debug(text_body)
    return html_body, text_body


def send_email(subject, body_html, body_text):
    """
    Send an e-mail through SES with both a text body and an HTML body.
    """

    # Sender and Recipients are configured from env vars.
    sender = os.environ["SENDER"]
    recipients = os.environ["RECIPIENTS"].split(",")

    # Python3 uses UTF-8
    charset = "UTF-8"

    # Send the email.
    try:
        response = ses_client.send_email(
            Destination={
                "ToAddresses": recipients,
            },
            Message={
                "Body": {
                    "Html": {
                        "Charset": charset,
                        "Data": body_html,
                    },
                    "Text": {
                        "Charset": charset,
                        "Data": body_text,
                    },
                },
                "Subject": {
                    "Charset": charset,
                    "Data": subject,
                },
            },
            Source=sender,
        )

    # Display an error if something goes wrong.
    except ClientError as e:
        LOG.exception(e)
    else:
        LOG.info(f"Email sent! Message ID: {response['MessageId']}")
