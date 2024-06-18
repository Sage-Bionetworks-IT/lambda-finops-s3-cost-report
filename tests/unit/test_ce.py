import pytest
from botocore.stub import Stubber

from email_totals import ce


def test_ce_accounts(mock_ce_period,
                     mock_ce_account_target_data):
    with Stubber(ce.ce_client) as _stub:
        _stub.add_response('get_cost_and_usage', mock_ce_account_target_data)

        # validate our stub response against boto
        ce.get_ce_account_costs(mock_ce_period)

        # assert that the client function was called
        _stub.assert_no_pending_responses()


def test_ce_emails(mock_ce_period,
                   mock_ce_email_target_data):
    with Stubber(ce.ce_client) as _stub:
        _stub.add_response('get_cost_and_usage', mock_ce_email_target_data)

        # validate our stub response against boto
        ce.get_ce_email_costs(mock_ce_period)

        # assert that the client function was called
        _stub.assert_no_pending_responses()


def test_ce_invalid_tags(mock_ce_invalid_tags_user1):
    with Stubber(ce.ce_client) as _stub:
        _stub.add_response('get_cost_and_usage_with_resources',
                           mock_ce_invalid_tags_user1)

        # validate our response
        ce.get_ce_invalid_tag_for_email('email')

        # assert no other responses
        _stub.assert_no_pending_responses()


@pytest.mark.parametrize(
    "mock_ce_fixture",
    [
        "mock_ce_missing_tags_user2",
        "mock_ce_missing_tags_user3"
    ]
)
def test_ce_missing_tags(mock_ce_fixture,
                         request):
    mock_ce_missing_tag_resources = request.getfixturevalue(mock_ce_fixture)
    with Stubber(ce.ce_client) as _stub:
        _stub.add_response('get_cost_and_usage_with_resources',
                           mock_ce_missing_tag_resources)

        # validate our stub response against boto
        ce.get_ce_missing_tag_for_email('email')

        # assert that the client function was called
        _stub.assert_no_pending_responses()
