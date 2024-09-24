import os

import pytest
from botocore.stub import Stubber

from s3_cost_report import ses


def test_send_email(mocker, mock_ses_response):
    text_body = "test"
    html_body = "<html>test</html>"
    subject = "Report: Test Month"

    env_vars = {
        "RECIPIENTS": "admin@example.com,cc@example.com",
        "SENDER": "test@example.com",
    }
    mocker.patch.dict(os.environ, env_vars)

    with Stubber(ses.ses_client) as _stub:
        _stub.add_response("send_email", mock_ses_response)

        ses.send_email(subject, html_body, text_body)

        # assert that the client function was called
        _stub.assert_no_pending_responses()


def test_email_body(mocker, mock_app_service_dict, mock_app_s3_usage_dict):
    # assert no exceptions are raised
    env_vars = {
        "MINIMUM": "0.01"
    }
    mocker.patch.dict(os.environ, env_vars)

    html, text = ses.build_email_body(mock_app_service_dict, mock_app_s3_usage_dict)
    print(html)
    print(text)
