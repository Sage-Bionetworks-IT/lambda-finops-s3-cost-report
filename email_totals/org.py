import logging

import boto3

LOG = logging.getLogger(__name__)
LOG.setLevel(logging.DEBUG)

# Create organizations client for getting account tags
org_client = boto3.client('organizations')

# Name of the account tag containing an account owner
account_owner_tag = 'AccountOwner'


def get_account_owners():
    """
    Get account owner tags from organizations client and return a mapping
    of owners to accounts:
    ```
    owner1@exapmle.com:
        - 111122223333
        - 222233334444
    owner2@example.com:
        - 333344445555
    ```
    """

    account_owners = {}

    # paginate list of accounts
    account_pages = org_client.get_paginator('list_accounts').paginate()

    # check for tags on each account
    for account_page in account_pages:
        for account in account_page['Accounts']:
            account_id = account['Id']

            tag_pager = org_client.get_paginator('list_tags_for_resource')
            tag_pages = tag_pager.paginate(ResourceId=account_id)

            owner = None
            for tag_page in tag_pages:
                for tag in tag_page['Tags']:
                    if tag['Key'] == account_owner_tag:
                        owner = tag['Value']

                        if owner not in account_owners:
                            account_owners[owner] = []

                        account_owners[owner].append(account_id)

                        # stop processing tags for this page
                        break

                if owner is not None:
                    # stop processing tag pages for this account
                    break

    LOG.debug(account_owners)
    return account_owners
