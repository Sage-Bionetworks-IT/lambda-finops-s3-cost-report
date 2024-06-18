import os

import pytest

# This needs to be set when the modules are loaded,
# but its value is not used when running tests
os.environ["AWS_DEFAULT_REGION"] = "test-region"
from email_strides import ce

# Constants used by fixtures

ce_period = {"Start": "2023-01-01", "End": "2023-02-01"}

# Set up the test scenario used by all tests
#
# There are three mock service totals: one is typical, the second is lacking
# comparison data, and the third is less than the minimum value to report.
# There are also three mock S3 usage types: the first tests with a zero for the
# previous month, the second tests with a zero for the current month, and the
# third tests with both zeros (simulating fractions of a cent rounded down).

service1_name = "ec2"
service1_total = 30.0
service1_previous = 20.0
service1_change = 0.5

service2_name = "s3"
service2_total = 123.45
service2_change = 1.0

service3_name = "lambda"
service3_total = 0.001
service3_change = 0.0

s3_usage_type1_name = "type1"
s3_usage_type1_total = 25.0
s3_usage_type1_previous = 0.0
s3_usage_type1_change = 1.0

s3_usage_type2_name = "type2"
s3_usage_type2_total = 0.0
s3_usage_type2_previous = 10
s3_usage_type2_change = -1.0

s3_usage_type3_name = "type3"
s3_usage_type3_total = 0.0
s3_usage_type3_previous = 0.0
s3_usage_type3_change = 0.0


# App fixtures


@pytest.fixture()
def mock_app_service_dict():
    response = {
        service1_name: {
            "total": service1_total,
            "change": service1_change,
        },
        service2_name: {
            "total": service2_total,
            "change": service2_change,
        },
    }
    return response


@pytest.fixture()
def mock_app_s3_usage_dict():
    response = {
        s3_usage_type1_name: {
            "total": s3_usage_type1_total,
            "change": s3_usage_type1_change,
        },
        s3_usage_type2_name: {
            "total": s3_usage_type2_total,
            "change": s3_usage_type2_change,
        },
        s3_usage_type3_name: {
            "total": s3_usage_type3_total,
            "change": s3_usage_type3_change,
        },
    }
    return response


# CE fixtures


def mock_ce_response(data):
    groups = []

    for key, amount in data.items():
        group = {
            "Keys": [
                key,
            ],
            "Metrics": {ce.cost_metric: {"Amount": str(amount)}},
        }
        groups.append(group)

    response = {
        "GroupDefinitions": [
            {"Type": "DIMENSION", "Key": "SERVICE"},
        ],
        "ResultsByTime": [
            {"TimePeriod": ce_period, "Total": {}, "Groups": groups, "Estimated": False}
        ],
    }
    return response


@pytest.fixture()
def mock_ce_service_target_data():
    target_totals = {
        service1_name: service1_total,
        service2_name: service2_total,
        service3_name: service3_total,
    }
    return mock_ce_response(target_totals)


@pytest.fixture()
def mock_ce_service_compare_data():
    compare_totals = {
        service1_name: service1_previous,
    }
    return mock_ce_response(compare_totals)


@pytest.fixture()
def mock_ce_s3_usage_target_data():
    target_totals = {
        s3_usage_type1_name: s3_usage_type1_total,
        s3_usage_type2_name: s3_usage_type2_total,
        s3_usage_type3_name: s3_usage_type3_total,
    }
    return mock_ce_response(target_totals)


@pytest.fixture()
def mock_ce_s3_usage_compare_data():
    compare_totals = {
        s3_usage_type1_name: s3_usage_type1_previous,
        s3_usage_type2_name: s3_usage_type2_previous,
        s3_usage_type3_name: s3_usage_type3_previous,
    }
    return mock_ce_response(compare_totals)


@pytest.fixture()
def mock_ce_period():
    return ce_period


# SES fixtures


@pytest.fixture()
def mock_ses_response():
    response = {"MessageId": "testId"}
    return response
