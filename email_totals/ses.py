import json
import logging
import os
import time

import boto3
from botocore.config import Config as BotoConfig
from botocore.exceptions import ClientError

LOG = logging.getLogger(__name__)
LOG.setLevel(logging.DEBUG)

sagebase_email = '@sagebase.org'
sagebio_email = '@sagebionetworks.org'
synapse_email = '@synapse.org'

# Use standard mode in order to retry on RequestLimitExceeded
# and increase the default number of retries to 10
ses_config = BotoConfig(
    retries = {
        'mode': 'standard',  # default mode is legacy
        'max_attempts': 10,  # default for standard mode is 3
    }
)
ses_client = boto3.client('ses', config=ses_config)


def _table_row_style(i):
    """
    Alternating table row background colors
    """
    if i % 2 == 0:
        return "style='background-color: WhiteSmoke;'"
    else:
        return ""


def build_paragraph(text, html=False):
    output = ''

    if html:
        # Put the paragraph in an invisible table to wrap long lines;
        # give the table a single row with two cells, put the text in
        # the first cell and let the second cell fill any extra space
        output += ("<table border='0' width='100%' "
                   "style='border-collapse: collapse;'><tr>"
                   f"<td width='600'>{text}</td><td></td>"
                   "</tr></table>")
    else:
        output += text + '\n'

    return output


def build_tags_table(missing, invalid, account_names, html=False):
    """
    Build a table about missing or invalid CostCenterOther tags
    """
    output = ''
    row_i = 0  # row index for coloring table rows

    if html:
        output += ("<table border='1' padding='10' width='600' "
                   "style='border-collapse: collapse; text-align: center;'>"
                   "<tr style='background-color: LightSteelBlue'>"
                   "<th>Account Name (Account ID)</th>")
        if missing:
            output += "<th>Resources missing CostCenterOther tags</th>"
        if invalid:
            output += "<th>Resources with unexpected CostCenterOther tags</th></tr>"
    else:
        output += 'Account Name (Account ID)'
        if missing:
            output += '\tResources missing CostCenterOther tags'
        if invalid:
            output += '\tResources with unexpected CostCenterOther tags'
        output += '\n'

    accounts = []
    for account_id in missing:
        accounts.append(account_id)
    for account_id in invalid:
        accounts.append(account_id)
    LOG.debug(f"Accounts: {accounts}")

    for account_id in accounts:
        account_name = account_names[account_id]

        # Convert list to string
        untagged = ''
        if account_id in missing:
            untagged = json.dumps(missing[account_id])
        unexpected = ''
        if account_id in invalid:
            unexpected = json.dumps(invalid[account_id])

        if html:
            _td = f"<td>{account_name} ({account_id})</td>"
            if missing:
                _td += f"<td>{untagged}</td>"
            if invalid:
                _td += f"<td>{unexpected}</td>"

            _style = _table_row_style(row_i)
            output += f"<tr {_style}>{_td}</tr>"
            row_i += 1

        else:
            _td = f"{account_name} ({account_id})"
            if missing:
                _td += f"\t{untagged}"
            if invalid:
                _td += f"\t{unexpected}"
            output += f"{_td}\n"

    if html:
        output += "</table><br/>"

    return output


def build_usage_table(usage, account_names, total=None, html=False):
    """
    Build table about directly-tagged resources

    Example usage block:
    ```
    111122223333:
        total: 10.0
    222233334444:
        total: 20.0
        change: 0.5
    ```
    """

    output = ''

    # customize total header in unowned report
    if total is None:
        total = 'Your Total'

    if html:
        output += ("<table border='1' padding='10' width='600' "
                   "style='border-collapse: collapse; text-align: center;'>"
                   "<tr style='background-color: LightSteelBlue'>"
                   "<th>Account Name (Account ID)</th>"
                   f"<th>{total}</th><th>Month-over-Month Change</th></tr>")
        row_i = 0  # row index for coloring table rows
    else:
        output += '\t'.join(['Account Name (Account ID)',
                             total, 'Month-over-Month Change']) + '\n'

    for account_id in usage:
        account_name = account_names[account_id]

        # Round dollar total to 2 decimal places
        total = f"${usage[account_id]['total']:.2f}"

        change = ''
        if 'change' in usage[account_id]:
            # Convert to a percentage
            change = f"{usage[account_id]['change']:.2%}"

        if html:
            _td = (f"<td>{account_name} ({account_id})</td>"
                   f"<td>{total}</td><td>{change}</td>")

            _style = _table_row_style(row_i)
            output += f"<tr {_style}>{_td}</tr>"
            row_i += 1

        else:
            _td = [account_name, account_id, total, change]
            output += '\t'.join(_td) + '\n'

    if html:
        output += "</table><br/>"

    return output


def valid_recipient(email, team_sage):
    """
    Determine if a given recipient should receive an email
    """

    restrict = os.environ['RESTRICT']
    approved = os.environ['APPROVED'].split(',')
    skiplist = os.environ['SKIPLIST'].split(',')

    # Skip anyone who has opted out
    if email in skiplist:
        LOG.info(f"Skipping address: '{email}'")
        return False

    # If sending is restricted, check the approved list
    if restrict == 'True':
        if email in approved:
            return True
        LOG.info(f"Restricted, skipping address: '{email}'")
        return False

    # Check for internal domains
    if email.endswith(sagebase_email) or email.endswith(sagebio_email):
        return True

    # Check Synapse users against Team Sage
    if email.endswith(synapse_email):
        if email in team_sage:
            return True

        LOG.info(f"Skipping external synapse user: '{email}'")
        return False

    # Not all tag values are valid email addresses, and uncategorized
    # costs will be associated with an empty string value
    LOG.warning(f"Invalid email address: '{email}'")
    return False


def build_user_email_body(summary, account_names):
    """
    Generate an HTML and a plain-text message body for a user summary entry
    """

    def _build_accounts_usage(usage, html=False):
        """
        Build paragraph about owned accounts

        Example usage block:
        ```
        333344445555:
            total: 200.0
            change: -0.05
        444455556666:
            total: 1.0
        ```
        """

        output = ''

        descr = 'You are tagged as owning the following accounts:'

        output += build_paragraph(descr, html)
        output += build_usage_table(usage, account_names, total='Account Total', html=html)

        return output

    def _build_resource_usage(resource_usage, account_usage=None, html=False):
        """
        Build paragraph about directly-tagged resources, omitting any resources
        that are in accounts owned by the user.

        Example usage block:
        ```
        111122223333:
            total: 10.0
        222233334444:
            total: 20.0
            change: 0.5
        ```
        """

        output = ''

        descr = ('You are tagged as owning resources in the following '
                 'accounts: ')

        # Don't report resources if we also own the account
        if account_usage is not None:
            for account_id in account_usage:
                if account_id in resource_usage:
                    del resource_usage[account_id]

        # Only generate output if we still have resource usage
        if resource_usage:
            output += build_paragraph(descr, html)
            output += build_usage_table(resource_usage, account_names, html=html)

        return output

    def _build_tags(missing, invalid, html=False):
        """
        Build paragraph about missing or invalid CostCenterOther tags

        Example input block:
        ```
        111122223333:
            - i-0abcdefg
        333344445555:
            - i-1hijklmnop
        ```
        """

        descr_missing = ('Some of the above resources have a "CostCenter" tag '
                         'value of "Other / 000001" but do not have a required '
                         '"CostCenterOther" tag. ')

        descr_invalid = ('Some of the above resources have a "CostCenterOther" '
                         'tag, but do not have "CostCenter" set to "Other / 000001". ')

        descr_help = ('To accurately track project-related costs, a cost center must '
                      'be specified. If you need help updating tags, contact Sage IT.')
        descr = ''
        if missing:
            descr += descr_missing
        if invalid:
            descr += descr_invalid
        descr += descr_help

        output = ''
        output += build_paragraph(descr, html)
        output += build_tags_table(missing, invalid, account_names, html)

        return output

    title = 'AWS Monthly Cost Report Summary'
    intro = ('You are receiving this summary because you are tagged as '
             'the owner of AWS resources.')

    html_body = f"<h3>{title}</h3>"
    html_body += build_paragraph(f"<p>{intro}</p>", True)

    text_body = f"{title}\n{intro}\n"

    if 'resources' in summary and summary['resources']:
        if 'accounts' in summary and summary['accounts']:
            html_body += _build_resource_usage(summary['resources'],
                                               summary['accounts'],
                                               html=True)
            text_body += _build_resource_usage(summary['resources'],
                                               summary['accounts'],
                                               html=False)
        else:
            html_body += _build_resource_usage(summary['resources'],
                                               html=True)
            text_body += _build_resource_usage(summary['resources'],
                                               html=False)

    if 'accounts' in summary:
        html_body += _build_accounts_usage(summary['accounts'], True)
        text_body += _build_accounts_usage(summary['accounts'], False)

    invalid_summary = {}
    missing_summary = {}
    if 'missing_other_tag' in summary:
        missing_summary = summary['missing_other_tag']
        LOG.debug(f"Missing CostCenterOther: {missing_summary}")
    if 'invalid_other_tag' in summary:
        invalid_summary = summary['invalid_other_tag']
        LOG.debug(f"Unexpected CostCenterOther: {invalid_summary}")

    if invalid_summary or missing_summary:
        html_body += _build_tags(missing_summary, invalid_summary, True)
        text_body += _build_tags(missing_summary, invalid_summary, False)
    else:
        LOG.debug("Skipping CostCenterOther section")

    docs_prose = ('You can use AWS Cost Explorer to analyze these expenses by '
                  'filtering on the "Owner Email" category and/or account ID')
    docs_name = 'Using AWS Cost Explorer'
    docs_url = 'https://sagebionetworks.jira.com/wiki/spaces/IT/pages/2756935685/Using+AWS+Cost+Explorer'

    html_body += build_paragraph(f"{docs_prose}: <a href='{docs_url}'>{docs_name}</a>", True)
    text_body += f"\n{docs_prose}. See '{docs_name}' at: {docs_url}"

    LOG.debug(html_body)
    LOG.debug(text_body)
    return html_body, text_body


def build_unowned_email_body(unowned_data, account_names):
    """
    Generate an email body summarizing unowned costs
    """

    title = 'AWS Monthly Unowned Cost Summary'
    prose = 'The following costs do not have a tagged owner to notify:'

    html_body = f"<h3>{title}</h3>"
    text_body = f"{title}\n\n"

    html_body += build_paragraph(prose, True)
    text_body += build_paragraph(prose, False)

    html_body += build_usage_table(unowned_data,
                                   account_names,
                                   'Unowned Costs',
                                   True)

    text_body += build_usage_table(unowned_data,
                                   account_names,
                                   'Unowned Costs',
                                   False)

    LOG.debug(html_body)
    LOG.debug(text_body)
    return html_body, text_body


def add_cc_list(primary):
    """
    Add the CC addresses to the list of recipients, if any
    """
    recipients = [primary, ]
    cc_list = os.environ['CC_LIST'].split(',')
    if cc_list != ['']:
        recipients.extend(cc_list)
    return recipients


def send_report_email(recipient, body_html, body_text, period):
    """
    Send a per-user report email
    """
    subject = f"AWS Monthly Cost Report ({period})"
    recipients = add_cc_list(recipient)
    send_email(recipients, subject, body_html, body_text)


def send_unowned_email(body_html, body_text, period):
    """
    Send a report on unowned costs to the admin recipient
    """
    subject = f"AWS Unowned Costs ({period})"
    admin = os.environ['ADMIN_EMAIL']
    recipients = add_cc_list(admin)
    send_email(recipients, subject, body_html, body_text)


def send_email(recipients, subject, body_html, body_text):
    """
    Send e-mail through SES
    """

    sender = os.environ['SENDER']

    # Python3 uses UTF-8
    charset = "UTF-8"

    # Try to send the email.
    try:
        response = ses_client.send_email(
            Destination={
                'ToAddresses': recipients,
            },
            Message={
                'Body': {
                    'Html': {
                        'Charset': charset,
                        'Data': body_html,
                    },
                    'Text': {
                        'Charset': charset,
                        'Data': body_text,
                    },
                },
                'Subject': {
                    'Charset': charset,
                    'Data': subject,
                },
            },
            Source=sender,
        )

    # Display an error if something goes wrong.
    except ClientError as e:
        LOG.exception(e)
    else:
        LOG.info(f"Email sent! Message ID: {response['MessageId']}")
