import pytest
from botocore.stub import Stubber

from s3_cost_report import ce


def test_ce_service(mock_ce_period, mock_ce_service_target_data):
    with Stubber(ce.ce_client) as _stub:
        _stub.add_response("get_cost_and_usage", mock_ce_service_target_data)

        # validate our stub response against boto
        ce.get_ce_service_costs(mock_ce_period)

        # assert that the client function was called
        _stub.assert_no_pending_responses()


def test_ce_s3_usage(mock_ce_period, mock_ce_s3_usage_target_data):
    with Stubber(ce.ce_client) as _stub:
        _stub.add_response("get_cost_and_usage", mock_ce_s3_usage_target_data)

        # validate our stub response against boto
        ce.get_ce_s3_usage_costs(mock_ce_period)

        # assert that the client function was called
        _stub.assert_no_pending_responses()
