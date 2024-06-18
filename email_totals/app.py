import logging
import os
from datetime import datetime

from email_totals import ce, org, synapse, ses

LOG = logging.getLogger(__name__)
LOG.setLevel(logging.DEBUG)


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
        target_period['Start'] = f'{today.year - 1}-12-01'
        target_period['End'] = f'{today.year}-01-01'

        compare_period['Start'] = f'{today.year - 1}-11-01'
        compare_period['End'] = f'{today.year - 1}-12-01'

    elif today.month == 2:
        # in Feb, look at Jan of this year and Dec of last year
        target_period['Start'] = f'{today.year}-01-01'
        target_period['End'] = f'{today.year}-02-01'

        compare_period['Start'] = f'{today.year - 1}-12-01'
        compare_period['End'] = f'{today.year}-01-01'

    else:
        # no year boundary, look at the previous two months
        target_period['Start'] = f'{today.year}-{(today.month - 1):02}-01'
        target_period['End'] = f'{today.year}-{today.month:02}-01'

        compare_period['Start'] = f'{today.year}-{(today.month - 2):02}-01'
        compare_period['End'] = f'{today.year}-{(today.month - 1):02}-01'

    LOG.info(f"Target month: {target_period}")
    LOG.info(f"Compare month: {compare_period}")

    return target_period, compare_period


def get_resource_totals(target_period, compare_period, minimum_total):
    """
    Get email cost information from cost explorer for both time periods
    and generate a multi-level dictionary. The top-level key will be the
    email address of the resource owner, the first-level subkey will be the
    literal string 'resources', the second-level subkey will be the account ID,
    and the third-level subkeys will be the literal strings 'total', and
    optionally 'change'; 'total' will map to a float representing the user's
    resource total for this account, and if 'change' is present it will map to a
    float representing percent change from the last month (1.0 is 100% growth).
    As a special case, a top-level key equal to the empty string will contain
    data for resources with no owner.

    Example:
    ```
    email1@example.com:
        resources:
            111122223333:
                total: 10.0
                change: -0.1
    email2@example.com:
        resources:
            222233334444:
                total: 2.1
    ```
    """

    def _build_dict(results_by_time, compare=None):
        """
        Build our simple data structure from the cost explorer results,
        optionally adding a percent change against compare data (if present).
        """
        resources = {}
        for result in results_by_time:
            for group in result['Groups']:
                amount = float(group['Metrics'][ce.cost_metric]['Amount'])

                # Keys preserve the order defined in the GroupBy parameter from
                # the call to get_cost_and_usage().
                if len(group['Keys']) != 2:
                    LOG.error(f"Unexpected grouping: {group['Keys']}")
                    continue

                # The category key has the format "<category name>$<category value>"
                # so everything after the first '$' will be the email address
                # A special case of "<category name>$" is used for uncategorized costs
                # giving us an empty-string email for costs with no owner
                # Downcase all emails to detect case-insensitive duplicates.
                email = group['Keys'][0].split('$', maxsplit=1)[1].lower()

                account_id = group['Keys'][1]

                if email == '':
                    LOG.debug(f"Unowned costs in account {account_id}: {amount}")

                # Skip insignificant totals
                if amount < minimum_total:
                    LOG.info(f"Skipping total less than ${minimum_total} for "
                             f"{email}: {account_id} ${amount}")
                    continue

                # Add 'resources' subkey if this is the first account we're
                # processing for this email
                if email not in resources:
                    resources[email] = {'resources': {}}

                # If this account is already listed, the email is a duplicate
                # this can happen if it is tagged with different casing.
                if account_id in resources[email]['resources']:
                    LOG.debug(f"duplicate entry found")
                    resources[email]['resources'][account_id]['total'] += amount
                else:
                    resources[email]['resources'][account_id] = {'total': amount}

                # If we have a compare dict, calculate a percent change
                if compare and email in compare:
                    _compare = compare[email]['resources']
                    if account_id in _compare:
                        # Calculate percent change from compare month
                        pct = (amount / _compare[account_id]['total']) - 1
                        resources[email]['resources'][account_id]['change'] = pct

        return resources

    # First generate data to compare against
    compare_data = ce.get_ce_email_costs(compare_period)
    compare_dict = _build_dict(compare_data['ResultsByTime'])

    # Then generate data our target data, passing in compare data
    target_data = ce.get_ce_email_costs(target_period)
    target_dict = _build_dict(target_data['ResultsByTime'], compare_dict)

    return target_dict


def get_account_totals(target_period, compare_period, minimum_total):
    """
    Get account cost information from cost explorer for both time periods,
    and also account owner tags from organizations, then generate and return
    a tuple of two dictionaries.

    The first is a multi-level dictionary where the top-level key will be the
    email address of the account owner, the first-level subkey will be the
    literal string 'accounts', the second-level subkey will be the account ID,
    and the third-level subkeys will be the literal string 'total', and
    optionally 'change'; 'total' will map to a float representing the account
    total, and if 'change' is present it will map to a float representing
    percent change from the last month (1.0 is 100% growth).

    The second is a simple dictionary mapping account IDs to their names.

    Example:
    ```
    email1@example.com:
        accounts:
            111122223333:
                total: 100.0
                change: 0.5
    email2@example.com:
        accounts:
            222233334444:
                total: 10
    ```

    ```
    111122223333: friendly-name
    222233334444: account-two
    ```
    """

    def _build_result_dict(results_by_time):
        """
        Transform the account results from cost explorer into a dictionary
        mapping account IDs to account totals for easy lookup.

        Example:
        ```
        111122223333: 100.0
        222233334444: 10
        ```
        """
        account_totals = {}
        for result in results_by_time:
            for group in result['Groups']:
                amount = float(group['Metrics'][ce.cost_metric]['Amount'])

                # Keys preserve the order defined in the GroupBy parameter from
                # the call to get_cost_and_usage().
                if len(group['Keys']) != 1:
                    LOG.error(f"Unexpected grouping: {group['Keys']}")
                    continue

                # Add this account total to our output
                account_id = group['Keys'][0]
                if account_id not in account_totals:
                    account_totals[account_id] = amount
                else:
                    LOG.error(f"Duplicate account total found: {account_id}")

        return account_totals

    def _build_attr_dict(attributes):
        """
        Transform DimensionValueAttributes into a simple dictionary so that we
        can easily look up a description for an arbitrary value.

        Original structure:
        ```
        [
          {
            'Value': value1
            'Attributes': {
              'description': description1
            }
          },
          {
            'Value': value2
            'Attributes': {
              'description': description2
            }
          }
        ]
        ```

        Transformed structure:
        ```
        value1: description1
        value2: description2
        ```
        """
        attr_dict = {}

        for item in attributes:
            value = item['Value']
            description = item['Attributes']['description']
            attr_dict[value] = description

        return attr_dict

    output = {}

    compare_ce_data = ce.get_ce_account_costs(compare_period)
    compare_dict = _build_result_dict(compare_ce_data['ResultsByTime'])

    target_ce_data = ce.get_ce_account_costs(target_period)
    target_dict = _build_result_dict(target_ce_data['ResultsByTime'])

    account_names = _build_attr_dict(target_ce_data['DimensionValueAttributes'])
    account_owners = org.get_account_owners()

    # Build an accounts subkey for each account owner
    for owner in account_owners:
        account_dict = {'accounts': {}}

        for account in account_owners[owner]:
            if account not in target_dict:
                # Every account in our organization should be in the dict
                LOG.error(f"No current total for account: {account}")
                continue

            target_total = target_dict[account]

            # Skip insignificant totals
            if target_total < minimum_total:
                LOG.info(f"Skipping total less than ${minimum_total} for {owner}: "
                         f"{account} ${target_total}")
                continue

            account_dict['accounts'][account] = {'total': target_total}

            # If we have a compare dict, calculate percent change
            if account in compare_dict:
                compare_total = compare_dict[account]
                pct_change = (target_total / compare_total) - 1
                account_dict['accounts'][account]['change'] = pct_change

        # Only add the subkey for the owner if its not empty
        if account_dict['accounts']:
            output[owner] = account_dict

    return output, account_names


def _parse_ce_tag_results(result_data):
    """
    Parse data returned by cost explorer and generate a dictionary mapping
    an account ID to a list of resource IDs.

    Example:
    ```
    111122223333:
      - i-0abcdefg
      - i-1hijkmln
    ```
    """

    output = {}

    for result in result_data['ResultsByTime']:
        for group in result['Groups']:
            # Keys preserve the order defined in the GroupBy parameter from
            # the call to get_cost_and_usage().
            if len(group['Keys']) != 2:
                LOG.error(f"Unexpected grouping: {group['Keys']}")
                continue

            account_id = group['Keys'][0]
            resource = group['Keys'][1]

            # Ignore entries with no resource ID
            if resource == 'NoResourceId':
                continue

            # Create initial list if needed
            if account_id not in output:
                output[account_id] = []

            # Add this resource to the account
            output[account_id].append(resource)

    return output


def get_invalid_other_tags(owner):
    """
    Query cost explorer for resource usage by the given resource owner,
    filtering for resources with an unexpected CostCenterOther tag (i.e.
    CostCenter is not set to Other).
    """

    invalid_data = ce.get_ce_invalid_tag_for_email(owner)
    invalid_tags = _parse_ce_tag_results(invalid_data)
    return invalid_tags


def get_missing_other_tags(owner):
    """
    Query cost explorer for resource usage by the given resource owner,
    filtering for resources missing a required CostCenterOther tag.
    """

    missing_data = ce.get_ce_missing_tag_for_email(owner)
    missing_tags = _parse_ce_tag_results(missing_data)
    return missing_tags


def build_summary(target_period, compare_period, team_sage):
    """
    Build a complex data structure representing the input needed for email
    templating.

    The first function parameter is a TimePeriod dict representing the month we
    are reporting on. The second parameter is a TimePeriod dict representing the
    month prior to the target month, for calculating percent change. The third
    parameter is a list of valid synapse users for receiving notifications.

    The top-level data structure is a dictionary with three static keys:
    'account_names', 'per_user_summary', and 'unowned'.

    The 'account_names' key maps to a dictionary keyed on account IDs and
    mapping them to their friendly names.

    The 'per_user_summary' key will map to a dictionary keyed on recipient email
    addresses, and will include 3 subkeys under each recipient: 'resources',
    'missing_other_tag', and 'accounts'.

    The 'resources' subkey will have per-account resource totals for the owner,
    and percent change from the previous month if applicable.

    The 'missing_other_tag' subkey will list owner resources that are missing a
    required 'CostCenterOther' tag.

    The 'invalid_other_tag' subkey will list owner resources tagged with a
    'CostCenterOther' tag without 'CostCenter' set to 'Other'.

    Since IT-2369 is blocked, the owner category does not include accounts
    tagged with an account owner. As a workaround, we add an 'accounts' subkey
    with account totals for owned accounts, and build an additional email
    section from it. If IT-2369 is ever implemented, then the owned accounts
    would be included in the 'resources' subkey and the 'accounts' subkey can
    be removed.

    The 'unowned' key will map to a dictionary keyed on account IDs, and
    each account ID will have a 'total' and 'change' subkey representing the
    total cost of unowned resources in the account and the percent change from
    the previous month, respectively.

    Example output
    ```
    account_names:
        111122223333: account-one
        222233334444: account-two
        333344445555: account-three
    per_user_summary:
        user1@example.com:
            resources:
                111122223333:
                    total: 10.0
                    change: 1.2
                222233334444:
                    total: 0.1
                    change: 0.0
            missing_other_tag:
                111122223333:
                  - i-0abcdefg
            accounts:
                333344445555:
                    total: 20.0
                    change: -2.1
        user2@example.com:
            ...
    unowned:
        111122223333:
            total: 1.2
            change: 0.0
    ```
    """

    data = {}
    min_value = float(os.environ['MINIMUM'])

    # Generate 'resources' subkeys under 'per_user_summary'
    resources_by_owner = get_resource_totals(target_period, compare_period, min_value)
    LOG.debug(f"Resource data: {resources_by_owner}")

    # Unowned resource costs will be associated with an empty string owner,
    # use pop() to remove the unowned data from the dictionary.
    # While IT-2369 is blocked the data will also include account totals for
    # accounts tagged with an owner, remove them as they are discovered.
    unowned = {}
    if '' in resources_by_owner:
        unowned = resources_by_owner.pop('')['resources']

    # Merge in the categorized resource data
    for owner in resources_by_owner:
        if owner not in data:
            data[owner] = {}
        data[owner]['resources'] = resources_by_owner[owner]['resources']

    # Generate 'accounts' subkeys
    accounts_dict, account_names = get_account_totals(target_period,
                                                      compare_period,
                                                      min_value)
    LOG.debug(f"Account data: {accounts_dict}")
    LOG.debug(f"Account names: {account_names}")

    # Merge in the account data, and remove from unowned
    for owner in accounts_dict:
        if owner not in data:
            data[owner] = {}

        accounts = accounts_dict[owner]['accounts']
        data[owner]['accounts'] = accounts

        for account in accounts:
            if account in unowned:
                LOG.debug(f"Account {account} is owned by {owner}")
                # remove owned account from unowned resources
                del unowned[account]

    LOG.debug(f"Uncategorized: {unowned}")
    LOG.debug(f"Unfiltered data: {data}")

    # Filter valid recipients and amend missing tag info
    filtered = {}
    for recipient in data:
        if ses.valid_recipient(recipient, team_sage):
            filtered[recipient] = data[recipient]

            # Amend summary with missing CostCenterOther tags
            # Do this after filtering to minimize CE calls
            missing_tags = get_missing_other_tags(recipient)
            if missing_tags:
                filtered[recipient]['missing_other_tag'] = missing_tags

            invalid_tags = get_invalid_other_tags(recipient)
            if invalid_tags:
                filtered[recipient]['invalid_other_tag'] = invalid_tags

    LOG.debug(f"Final summary: {filtered}")

    return {
        'account_names': account_names,
        'per_user_summary': filtered,
        'unowned': unowned,
    }


def lambda_handler(event, context):
    """
    Entry point

    Send monthly email reports to users with (1) tagged resource totals for the month,
    (2) tagged account totals for the month, and (3) resources missing a required
    CostCenterOther tag. Include month-over-month changes for both resource and
    account totals.
    """

    # Calculate the reporting periods to send to cost explorer
    now = datetime.now()
    target_month, compare_month = report_periods(now)

    # Name of the target period for the email subject
    _dt = datetime.fromisoformat(target_month['Start'])
    email_period = _dt.strftime("%B %Y")  # Month Year

    # Get Team Sage from Synapse
    team_sage = synapse.get_team_sage_members()

    # Build email summary
    summary = build_summary(target_month, compare_month, team_sage)
    per_user = summary['per_user_summary']
    accounts = summary['account_names']
    unowned = summary['unowned']

    # Create and send user reports from summary
    for email in per_user:
        user_html, user_text = ses.build_user_email_body(per_user[email], accounts)
        ses.send_report_email(email, user_html, user_text, email_period)

    # Create and send unowned report to admin
    unowned_html, unowned_text = ses.build_unowned_email_body(unowned, accounts)
    ses.send_unowned_email(unowned_html, unowned_text, email_period)
