import json
import time
from .base_task import BaseTask
from models.workspace import Workspace
from utils.context_utils import get_value
from exceptions.automation_framework_config_validation_exception import AutomationFrameworkValidationException
from utils.framework_state_manager import FrameworkStateManager
from logging import Logger

class PollDataPipeline(BaseTask):
    
    def __init__(self, fabric_client, context, logger: Logger, task_index):
        super().__init__(fabric_client, context, logger, task_index)

    def execute(self, **kwargs):

        workspace: Workspace = get_value('workspace', self.context, kwargs)
        item_id = get_value('item_id', self.context, kwargs)
        job_id = get_value('job_id', self.context, kwargs)

        framework_state_manager: FrameworkStateManager = self.context["framework_state_manager"]
        pipeline_id = self.context["pipeline_id"] 
        
        interval_in_secords = 20
        pipeline_activities = {}
        is_first_poll = True
        
        while True:

            job_instance = self.fabric_client.get_job_status(workspace.id, item_id, job_id)

            try:
                pipeline_activity_statuses = self.fabric_client.query_data_pipeline_status(workspace.id, job_id)
                for activity_details in pipeline_activity_statuses:
                    if "status" in activity_details and "activityRunId" in activity_details:
                        
                        activity_status = self.format_activity_status(activity_details["status"])
                        activity_id = activity_details["activityRunId"]
                        
                        if activity_id not in pipeline_activities:
                            details = {}
                            details["status"] = activity_status
                            details["pipelineName"] = activity_details.get("pipelineName", "")
                            details["activityName"] = activity_details.get("activityName", "")
                            details["pipelineRunId"] = activity_details.get("pipelineRunId", "")
                            details["activityRunStart"] = activity_details.get("activityRunStart", "")
                            details["activityRunEnd"] = activity_details.get("activityRunEnd", "")
                            details["endTime"] = activity_details.get("endTime", "")
                            details["error"] = activity_details.get("error", "")
                            details["output"] = activity_details.get("output", "")                            
                            pipeline_activities[activity_id] = details
                                                        
                            self.logger.info(f"pipeline activity {details['activityName']} status: {details['status']}")

                            framework_state_manager.register_task(
                                pipeline_id,
                                activity_id,
                                {
                                    "type": "data_pipeline_activity",
                                    "description": f"Running {details['activityName']} notebook activity",
                                    "parameters": {}
                                },
                                task_state=details["status"]
                            )
                            
                        else:
                            previous_activity_details = pipeline_activities[activity_id]
                            if activity_status != previous_activity_details["status"]:
                                self.logger.info(f"Activity {previous_activity_details['activityName']} status changed from {previous_activity_details['status']} to {activity_details['status']}")
                                
                                previous_activity_details["status"] = activity_status
                                
                                framework_state_manager.update_task_state(
                                    pipeline_id,
                                    activity_details["activityRunId"],
                                    activity_status,
                                    set_end_time=str(activity_status).lower() in ["complete", "failed", "succeeded", "cancelled"]
                                )

            except Exception as ex:
                self.logger.error(f"Error querying data pipeline status: {str(ex)}")

            if job_instance.status.lower() == 'completed':
                self.logger.info("Job completed successfully.")
                break

            elif job_instance.status.lower() == 'failed':
                if is_first_poll:
                    self.logger.info(f"Job status is failed on first poll, waiting {interval_in_secords} seconds...")
                    time.sleep(15)
                else:
                    self.logger.error("Job failed.")
                    break
            else:
                self.logger.info(f"Job status: {job_instance.status.lower()}. Polling again in {interval_in_secords} seconds...")
                time.sleep(interval_in_secords)
            
            is_first_poll = False

        self.logger.info(json.dumps(pipeline_activities, indent=2))

        return pipeline_activities


    def format_activity_status(self, activity_status: str):
        if activity_status.lower() == "completed":
            return "Completed"
        if activity_status.lower() == "succeeded":
            return "Completed"
        if activity_status.lower() == "inprogress":
            return "In Progress"
        if activity_status.lower() == "failed":
            return "Failed"
        if activity_status.lower() == "cancelled":
            return "Cancelled"
        else:
            activity_status

    def onComplete(self, **kwargs):
        pass
    
    def validate_args(self, **kwargs) -> bool:

        if "workspace" not in kwargs:
            raise AutomationFrameworkValidationException("workspace is required")
        
        if "item_id" not in kwargs:
            raise AutomationFrameworkValidationException("item_id is required")
        
        if "job_id" not in kwargs:
            raise AutomationFrameworkValidationException("job_id is required")