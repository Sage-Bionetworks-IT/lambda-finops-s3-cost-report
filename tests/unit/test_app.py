import os
from datetime import datetime

import pytest

from email_totals import app

# fixtures for datetime processing around year boundaries

# in december we target nov of this year
# and compare with oct of this year
test_now_dec = '2020-12-02'

expected_target_dec = {
    'Start': '2020-11-01',
    'End': '2020-12-01',
}

expected_compare_dec = {
    'Start': '2020-10-01',
    'End': '2020-11-01',
}

# in january we target dec of last year
# and compare with nov of last year
test_now_jan = '2020-01-02'

expected_target_jan = {
    'Start': '2019-12-01',
    'End': '2020-01-01',
}

expected_compare_jan = {
    'Start': '2019-11-01',
    'End': '2019-12-01',
}

# in february we target jan of this year
# and compare with dec of last year
test_now_feb = '2020-02-02'

expected_target_feb = {
    'Start': '2020-01-01',
    'End': '2020-02-01',
}

expected_compare_feb = {
    'Start': '2019-12-01',
    'End': '2020-01-01',
}

# minimum needs to be a float and will be respected
minimum = 1.0


# https://engineeringfordatascience.com/posts/pytest_fixtures_with_parameterize/


@pytest.mark.parametrize(
    "test_now,expected_target_period,expected_compare_period",
    [
        (test_now_dec, expected_target_dec, expected_compare_dec),
        (test_now_jan, expected_target_jan, expected_compare_jan),
        (test_now_feb, expected_target_feb, expected_compare_feb),
    ]
)
def test_report_periods(test_now,
                        expected_target_period,
                        expected_compare_period):
    test_dt = datetime.fromisoformat(test_now)
    found_target, found_compare = app.report_periods(test_dt)
    assert found_target == expected_target_period
    assert found_compare == expected_compare_period


def test_resource_totals(mocker,
                         mock_ce_period,
                         mock_ce_email_target_data,
                         mock_ce_email_compare_data,
                         mock_app_resource_dict):
    mocker.patch('email_totals.ce.get_ce_email_costs',
                 side_effect=[
                     mock_ce_email_compare_data,
                     mock_ce_email_target_data,
                 ])

    # target and compare periods are passed through to patched functions
    found_dict = app.get_resource_totals(mock_ce_period,
                                         mock_ce_period,
                                         minimum)

    assert found_dict == mock_app_resource_dict


def test_account_totals(mocker,
                        mock_app_account_dict,
                        mock_app_account_names,
                        mock_ce_account_target_data,
                        mock_ce_account_compare_data,
                        mock_ce_period,
                        mock_org_account_owners):
    mocker.patch('email_totals.ce.get_ce_account_costs',
                 side_effect=[
                     mock_ce_account_compare_data,
                     mock_ce_account_target_data,
                 ])

    mocker.patch('email_totals.org.get_account_owners',
                 return_value=mock_org_account_owners)

    # period input doesn't matter since it's only passed to patched functions
    found_dict, found_names = app.get_account_totals(mock_ce_period,
                                                     mock_ce_period,
                                                     minimum)
    assert found_names == mock_app_account_names
    assert found_dict == mock_app_account_dict


def test_invalid_other_tag(mocker,
                           mock_app_invalid_tags_user1,
                           mock_ce_invalid_tags_user1):
    mocker.patch('email_totals.ce.get_ce_invalid_tag_for_email',
                 return_value=mock_ce_invalid_tags_user1)

    found_invalid_tags = app.get_invalid_other_tags('ignored')
    assert found_invalid_tags == mock_app_invalid_tags_user1


@pytest.mark.parametrize(
    "mock_ce_fixture,mock_app_fixture",
    [
        ("mock_ce_missing_tags_user2", "mock_app_missing_tags_user2"),
        ("mock_ce_missing_tags_user3", "mock_app_missing_tags_user3"),

    ]
)
def test_missing_other_tag(mocker,
                           mock_app_fixture,
                           mock_ce_fixture,
                           request):
    mock_ce_missing_tags = request.getfixturevalue(mock_ce_fixture)
    mocker.patch('email_totals.ce.get_ce_missing_tag_for_email',
                 return_value=mock_ce_missing_tags)

    expected_app_missing_tags = request.getfixturevalue(mock_app_fixture)
    found_missing_tags = app.get_missing_other_tags('ignored')
    assert found_missing_tags == expected_app_missing_tags


def test_build_summary(mocker,
                       mock_app_resource_dict,
                       mock_app_account_dict,
                       mock_app_account_names,
                       mock_app_invalid_tags_user1,
                       mock_app_missing_tags_user2,
                       mock_app_missing_tags_user3,
                       mock_app_unowned,
                       mock_app_build_summary,
                       mock_ce_period,
                       mock_team_sage,
                       mock_user1,
                       mock_user2,
                       mock_user3):
    # The mocker will call the side_effect function with the same
    # arguments that were passed to the patched function
    def _missing_tags_side_effect(email):
        if email == mock_user2:
            return mock_app_missing_tags_user2
        if email == mock_user3:
            return mock_app_missing_tags_user3
        return {}

    def _invalid_tags_side_effect(email):
        if email == mock_user1:
            return mock_app_invalid_tags_user1
        return {}

    env_vars = {
        'MINIMUM': str(minimum),
    }
    mocker.patch.dict(os.environ, env_vars)

    mocker.patch('email_totals.app.get_resource_totals',
                 return_value=mock_app_resource_dict)

    mocker.patch('email_totals.app.get_account_totals',
                 return_value=(mock_app_account_dict, mock_app_account_names))

    mocker.patch('email_totals.app.get_missing_other_tags',
                 side_effect=_missing_tags_side_effect)

    mocker.patch('email_totals.app.get_invalid_other_tags',
                 side_effect=_invalid_tags_side_effect)

    mocker.patch('email_totals.ses.valid_recipient',
                 return_value=True)

    found_summary = app.build_summary(mock_ce_period,
                                      mock_ce_period,
                                      mock_team_sage)

    assert found_summary == mock_app_build_summary
