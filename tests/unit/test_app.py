import os
from datetime import datetime

import pytest
from botocore.stub import Stubber

from s3_cost_report import app


# fixtures for datetime processing around year boundaries

# in december we target nov of this year
# and compare with oct of this year
test_now_dec = "2020-12-02"

expected_target_dec = {
    "Start": "2020-11-01",
    "End": "2020-12-01",
}

expected_compare_dec = {
    "Start": "2020-10-01",
    "End": "2020-11-01",
}

# in january we target dec of last year
# and compare with nov of last year
test_now_jan = "2020-01-02"

expected_target_jan = {
    "Start": "2019-12-01",
    "End": "2020-01-01",
}

expected_compare_jan = {
    "Start": "2019-11-01",
    "End": "2019-12-01",
}

# in february we target jan of this year
# and compare with dec of last year
test_now_feb = "2020-02-02"

expected_target_feb = {
    "Start": "2020-01-01",
    "End": "2020-02-01",
}

expected_compare_feb = {
    "Start": "2019-12-01",
    "End": "2020-01-01",
}

@pytest.mark.parametrize(
    "test_now,expected_target_period,expected_compare_period",
    [
        (test_now_dec, expected_target_dec, expected_compare_dec),
        (test_now_jan, expected_target_jan, expected_compare_jan),
        (test_now_feb, expected_target_feb, expected_compare_feb),
    ],
)
def test_report_periods(test_now, expected_target_period, expected_compare_period):
    test_dt = datetime.fromisoformat(test_now)
    with Stubber(app.sts_client) as _sts:
        with Stubber(app.iam_client) as _iam:
            found_target, found_compare = app.report_periods(test_dt)
            assert found_target == expected_target_period
            assert found_compare == expected_compare_period


def test_service_costs(
    mocker,
    mock_ce_period,
    mock_ce_service_target_data,
    mock_ce_service_compare_data,
    mock_app_service_dict,
):
    env_vars = {
        "MINIMUM": "0.01"
    }
    mocker.patch.dict(os.environ, env_vars)

    mocker.patch(
        "s3_cost_report.ce.get_ce_service_costs",
        side_effect=[
            mock_ce_service_compare_data,
            mock_ce_service_target_data,
        ],
    )

    with Stubber(app.sts_client) as _sts:
        with Stubber(app.iam_client) as _iam:
            # target and compare periods are passed through to patched functions
            found_dict = app.get_service_costs(
                mock_ce_period,
                mock_ce_period,
            )
            assert found_dict == mock_app_service_dict


def test_s3_usage_costs(
    mocker,
    mock_app_s3_usage_dict,
    mock_ce_s3_usage_target_data,
    mock_ce_s3_usage_compare_data,
    mock_ce_period,
):
    env_vars = {
        "MINIMUM": "0"
    }
    mocker.patch.dict(os.environ, env_vars)

    mocker.patch(
        "s3_cost_report.ce.get_ce_s3_usage_costs",
        side_effect=[
            mock_ce_s3_usage_compare_data,
            mock_ce_s3_usage_target_data,
        ],
    )

    with Stubber(app.sts_client) as _sts:
        with Stubber(app.iam_client) as _iam:

            # period input doesn't matter since it's only passed to patched functions
            found_dict = app.get_s3_usage_costs(
                mock_ce_period,
                mock_ce_period,
            )
            assert found_dict == mock_app_s3_usage_dict
