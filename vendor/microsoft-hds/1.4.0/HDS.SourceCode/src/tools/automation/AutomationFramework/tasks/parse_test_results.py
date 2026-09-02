from azure.identity import DefaultAzureCredential
from azure.storage.filedatalake import DataLakeServiceClient
import json
import time
from datetime import datetime
import xml.etree.ElementTree as ET
from .base_task import BaseTask
from models.workspace import Workspace
from exceptions.automation_framework_runtime_exception import AutomationFrameworkRuntimeException
from exceptions.automation_framework_config_validation_exception import AutomationFrameworkValidationException
from utils.default_azure_credential_token_provider import DefaultAzureCredentialTokenProvider
from logging import Logger
import logging
from utils.context_utils import get_value
from utils.certificate_based_auth_token_provider import CertificateBasedAuthTokenProvider
from utils.custom_token_credential import CustomTokenCredential

class ParseTestResults(BaseTask):
    """
    Task to parse test result XML files from a Fabric Lakehouse, summarize results, and generate an HTML report.
    """
    def __init__(self, fabric_client, context, logger: Logger, task_index):
        super().__init__(fabric_client, context, logger, task_index)

    def execute(self, **kwargs):
        workspace, lakehouse, deployment_environment, test_name, token_provider, capacityId, resourceGroupName, subscriptionId = self._extract_args(kwargs)
        credential = self._get_credential(token_provider)
        test_name_with_date = f"{test_name}_{datetime.now().strftime('%d%b%Y')}"
        logging.getLogger('azure.core.pipeline.policies.http_logging_policy').setLevel(logging.WARNING)
        fs_client = self._get_filesystem_client(workspace, lakehouse, deployment_environment, credential)
        grouped_tests = self._collect_and_group_tests(fs_client)
        html_content, passed_tests, total_tests = self._generate_html_report(grouped_tests)
        self._write_html_report(html_content, test_name_with_date)
        self._log_console_summary(grouped_tests, test_name_with_date, passed_tests, total_tests)
        self._handle_capacity_pause_if_needed(capacityId, kwargs, subscriptionId, resourceGroupName)
        if passed_tests < total_tests:
            raise AutomationFrameworkRuntimeException(f"{test_name_with_date} test(s) failed")

    def _extract_args(self, kwargs):
        workspace = get_value('workspace', self.context, kwargs, None)
        lakehouse = get_value('lakehouse', self.context, kwargs)
        deployment_environment = get_value('deployment_environment', self.context, kwargs)
        test_name = get_value('test_name', self.context, kwargs)
        token_provider = get_value('token_provider', self.context, kwargs)
        capacityId = get_value('capacityId', self.context, kwargs)
        resourceGroupName = get_value('resourceGroup', self.context, kwargs)
        subscriptionId = get_value('subscriptionId', self.context, kwargs)
        return workspace, lakehouse, deployment_environment, test_name, token_provider, capacityId, resourceGroupName, subscriptionId

    def _get_credential(self, token_provider):
        if isinstance(token_provider, CertificateBasedAuthTokenProvider):
            return CustomTokenCredential(token_provider.get_storage_token(), time.time() + 3500)
        # CodeQL [SM05137] This code is used for local testing and not deployed in production.
        elif isinstance(token_provider, DefaultAzureCredentialTokenProvider):
            return DefaultAzureCredential()
        return None

    def _get_filesystem_client(self, workspace, lakehouse, deployment_environment, credential):
        account_url = f"https://{deployment_environment}-onelake.dfs.fabric.microsoft.com/{workspace.id}/{lakehouse.id}"
        self.logger.info(f"Getting results from: {account_url}")
        service_client = DataLakeServiceClient(account_url=account_url, credential=credential)
        return service_client.get_file_system_client("Files")

    def _collect_and_group_tests(self, fs_client):
        """Collect XML test results and group them by suite name."""
        grouped_tests = {}
        for path in list(fs_client.get_paths()):
            if 'xml' not in path.name:
                continue
            suite_name = self._extract_suite_name(path.name)
            file_path = path.name.split("Files")[-1]
            test_result_content_bytes = fs_client.get_file_client(file_path).download_file().readall()
            test_result_xml_content_str = test_result_content_bytes.decode('utf-8')
            root = ET.fromstring(test_result_xml_content_str)
            data_dict = self.xml_to_dict(root)
            data_dict = self.add_test_status(data_dict)
            if 'testsuite' in data_dict:
                testsuite = data_dict['testsuite']
                testcases = testsuite.get('testcase', [])
                if not isinstance(testcases, list):
                    testcases = [testcases]
                if suite_name not in grouped_tests:
                    grouped_tests[suite_name] = []
                grouped_tests[suite_name].extend(testcases)
        return grouped_tests

    def _extract_suite_name(self, path_name):
        parts = path_name.split('/')
        if len(parts) > 2:
            return parts[-2]
        elif len(parts) == 2:
            return parts[0].replace("Files", "") or "Unknown Suite"
        return "Unknown Suite"

    def _generate_html_report(self, grouped_tests):
        html_content = """
        <html>
        <head>
            <title>Test Results</title>
            <style>
                table { border-collapse: collapse; width: 60%%; margin-bottom: 30px;}
                th, td { border: 1px solid #ddd; padding: 8px; text-align: left;}
                th { background-color: #f2f2f2;}
                .succeeded { color: green; }
                .failed { color: red; }
                h2 { margin-top: 40px; }
            </style>
        </head>
        <body>
            <h1>Test Results Grouped by Testsuite</h1>
        """
        total_tests = 0
        passed_tests = 0
        suite_stats = {}
        for suite_name, testcases in grouped_tests.items():
            succeeded_tests = [test for test in testcases if test.get('status') == 'Succeeded']
            total_tests += len(testcases)
            passed_tests += len(succeeded_tests)
            suite_stats[suite_name] = (len(succeeded_tests), len(testcases))
        html_content += f"<p><b>Overall: Passed {passed_tests} / {total_tests} tests</b></p>"
        for suite_name, testcases in grouped_tests.items():
            succeeded_tests = [test for test in testcases if test.get('status') == 'Succeeded']
            failed_tests = [test for test in testcases if test.get('status') == 'Failed']
            suite_passed, suite_total = suite_stats[suite_name]
            html_content += f"<h2>Testsuite: {suite_name}</h2>"
            html_content += f"<p><b>Passed {suite_passed} / {suite_total} tests</b></p>"
            html_content += """
            <h3>Succeeded Tests</h3>
            <table>
                <tr><th>Test Name</th><th>Status</th></tr>
            """
            for test in succeeded_tests:
                html_content += f"<tr><td>{test.get('test_name', '')}</td><td class='succeeded'>{test.get('status', '')}</td></tr>"
            html_content += "</table>"
            html_content += """
            <h3>Failed Tests</h3>
            <table>
                <tr><th>Test Name</th><th>Status</th></tr>
            """
            for test in failed_tests:
                html_content += f"<tr><td>{test.get('test_name', '')}</td><td class='failed'>{test.get('status', '')}</td></tr>"
            html_content += "</table>"
        html_content += """
        </body>
        </html>
        """
        return html_content, passed_tests, total_tests

    def _write_html_report(self, html_content, test_name_with_date):
        html_file_path = f"integration_test_artifacts/test_results_{test_name_with_date}.html"
        with open(html_file_path, "w", encoding="utf-8") as f:
            f.write(html_content)
        self.logger.info(f"HTML report generated: {html_file_path}")

    def _log_console_summary(self, grouped_tests, test_name_with_date, passed_tests, total_tests):
        test_results = ""
        for suite_name, testcases in grouped_tests.items():
            test_results += f"\nTestsuite: {suite_name}\n"
            for test in testcases:
                test_results += f"Test: {test.get('test_name', '')}... {test.get('status', '')}\n"
        test_results += f"\n{test_name_with_date} Test Results: {passed_tests}/{total_tests}\n"
        self.logger.info(test_results)

    def _handle_capacity_pause_if_needed(self, capacityId, kwargs, subscriptionId, resourceGroupName):
        if not capacityId:
            return
        capacityResumed = get_value('capacityResumed', self.context, kwargs)
        if capacityResumed:
            capacity = self.fabric_client.get_capacity(capacityId)
            if capacity is None:
                raise AutomationFrameworkRuntimeException(f"Capacity with id {capacityId} not found.")
            capacityName = capacity.displayName
            self.logger.info(f"Pausing the resumed capacity with Id: {capacityName}")
            self.fabric_client.pause_capacity(capacityName, subscriptionId, resourceGroupName)
            self.logger.info(f"Paused the capacity with Id: {capacityName}")

    def xml_to_dict(self, element):
        if len(element) == 0:
            return element.attrib
        result = {}
        for child in element:
            child_result = self.xml_to_dict(child)
            if child.tag not in result:
                result[child.tag] = child_result
            else:
                if not isinstance(result[child.tag], list):
                    result[child.tag] = [result[child.tag]]
                result[child.tag].append(child_result)
        result.update(element.attrib)
        return result

    def add_test_status(self, data):
        if 'testsuite' in data:
            testsuite = data['testsuite']
            if 'testcase' in testsuite:
                testcases = testsuite['testcase']
                if not isinstance(testcases, list):
                    testcases = [testcases]
                for testcase in testcases:
                    if testcase is not None:
                        if 'failure' in testcase:
                            testcase['status'] = 'Failed'
                        else:
                            testcase['status'] = 'Succeeded'
                        if 'classname' in testcase:
                            del testcase['classname']
                        if 'name' in testcase:
                            testcase['test_name'] = testcase.pop('name').split('test_')[-1]
                        if 'system-out' in testcase:
                            del testcase['system-out']
                        if 'failure' in testcase:
                            del testcase['failure']
        return data

    def validate_args(self, **kwargs) -> bool:
        if "workspace" not in kwargs:
            raise AutomationFrameworkValidationException("ParseTestResults: workspace is a required parameter.")
        if "lakehouse" not in kwargs:
            raise AutomationFrameworkValidationException("ParseTestResults: lakehouse is a required parameter.")
        if "deployment_environment" not in kwargs:
            raise AutomationFrameworkValidationException("ParseTestResults: deployment_environment is a required parameter.")
        if "test_name" not in kwargs:
            raise AutomationFrameworkValidationException("ParseTestResults: test_name is a required parameter.")