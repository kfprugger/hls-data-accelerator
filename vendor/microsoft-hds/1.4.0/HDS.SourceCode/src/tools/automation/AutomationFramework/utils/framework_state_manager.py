import os
import datetime
import time
from typing import Dict
from uuid import uuid4
import threading

class FrameworkStateManager:

    def __init__(self, html_template_path="pipeline_status_template.html", output_file="integration_test_artifacts/pipeline_status.html"):
        self.html_template_path = html_template_path
        self.output_file = output_file
        self.pipeline_status = {}
        self.tasks = {}
        self.lock = threading.Lock()
        self.update_thread = threading.Thread(target=self.update_durations_periodically)
        self.update_thread.daemon = True
        self.update_thread.start()

    def register_pipeline(self, config_name, total_steps) -> str:
        pipeline_id = str(uuid4())
        with self.lock:
            self.pipeline_status[pipeline_id] = {
                "config_name": config_name,
                "state": "Queued",
                "start_time": "",
                "end_time": "",
                "duration": "0s",
                "task_index": 0,
                "total_steps": total_steps,
                "current_task_name": "",
                "details": "",
            }
        self.update_html()
        return pipeline_id

    def register_task(self, pipeline_id, task_id, task_config: Dict, task_state = "In Progress") -> str:
        with self.lock:
            if pipeline_id in self.pipeline_status:
                self.tasks[task_id] = {
                    "pipeline_id": pipeline_id,
                    "task_name": task_config.get("type", ""),
                    "task_description": task_config.get("description", ""),
                    "task_state": task_state,
                    "start_time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "end_time": "",
                    "duration": "0s",
                }
        self.update_html()
        return task_id

    def update_durations_periodically(self):
        while True:
            with self.lock:
                for pipeline_id, status in self.pipeline_status.items():
                    if status["start_time"] and status["state"] in ["Queued", "In Progress"]:
                        status["duration"] = self.calculate_duration(status["start_time"])

                for task_status in self.tasks.values():
                    if task_status["start_time"] and task_status["task_state"] in ["In Progress"]:
                        task_status["duration"] = self.calculate_duration(task_status["start_time"])
            self.update_html()
            time.sleep(15)

    def format_duration(self, duration):
        """Helper method to format duration in hours and minutes."""
        total_seconds = int(duration.total_seconds())
        hours, remainder = divmod(total_seconds, 3600)
        minutes, _ = divmod(remainder, 60)
        return f"{hours}h {minutes}m {total_seconds % 60}s"

    def calculate_duration(self, start_time):
        """Helper method to calculate the duration from start_time to the current time."""
        start_time_dt = datetime.datetime.strptime(start_time, "%Y-%m-%d %H:%M:%S")
        current_time_dt = datetime.datetime.now()
        duration = current_time_dt - start_time_dt
        return self.format_duration(duration)

    def update_task_state(self, pipeline_id, task_id, task_state=None, set_end_time=False):
        with self.lock:
            if pipeline_id in self.pipeline_status:
                if task_id not in self.tasks:
                    raise Exception(f"Task {task_id} updated before registered")
                if task_state is not None:
                    self.tasks[task_id]["task_state"] = task_state

                if set_end_time:
                    self.tasks[task_id]["end_time"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                self.tasks[task_id]["duration"] = self.calculate_duration(self.tasks[task_id]["start_time"])
                self.pipeline_status[pipeline_id]["tasks"] = self.tasks
        self.update_html()

    def update_task_description(self, pipeline_id, task_id, task_description=None):
        with self.lock:
            if pipeline_id in self.pipeline_status:
                if task_id not in self.tasks:
                    raise Exception(f"Task {task_id} updated before registered")
                if task_description is not None:
                    self.tasks[task_id]["task_description"] = task_description
        self.update_html()

    def update_pipeline_state(self, pipeline_id, state=None, set_end_time=None, duration=None, task_index=None, total_steps=None, current_task_name=None, details=None):

        with self.lock:
            if pipeline_id in self.pipeline_status:
                if state is not None:
                    self.pipeline_status[pipeline_id]["state"] = state
                if task_index is not None:
                    self.pipeline_status[pipeline_id]["task_index"] = task_index
                if total_steps is not None:
                    self.pipeline_status[pipeline_id]["total_steps"] = total_steps

                if current_task_name is not None:
                    self.pipeline_status[pipeline_id]["current_task_name"] = details
                else:
                    self.pipeline_status[pipeline_id]["current_task_name"] = ""

                if details is not None:
                    self.pipeline_status[pipeline_id]["details"] = details
                else:
                    self.pipeline_status[pipeline_id]["details"] = ""

                if self.pipeline_status[pipeline_id]["start_time"] != "":
                    duration = self.calculate_duration(self.pipeline_status[pipeline_id]["start_time"])
                    self.pipeline_status[pipeline_id]["duration"] = duration

                elif self.pipeline_status[pipeline_id]["start_time"] == "":
                    self.pipeline_status[pipeline_id]["start_time"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    self.pipeline_status[pipeline_id]["duration"] = "0h 0m 0s"

                if set_end_time:
                    self.pipeline_status[pipeline_id]["end_time"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                else:
                    self.pipeline_status[pipeline_id]["end_time"] = ""

            self.update_html()

    def update_html(self):

        script_dir = os.path.dirname(__file__)
        template_path = os.path.join(script_dir, self.html_template_path)
        with open(template_path, "r") as f:
            html_template = f.read()

        # Generate new table rows
        sorted_pipeline_statuses = sorted(self.pipeline_status.items(), key=lambda item: item[1]['state'])
        sorted_tasks_statuses = sorted(
            self.tasks.items(),
            key=lambda item: datetime.datetime.strptime(item[1]['start_time'], '%Y-%m-%d %H:%M:%S'))

        pipeline_table_rows = ""
        for pipeline_id, pipeline_status in sorted_pipeline_statuses:
            pipeline_table_rows += f"""
            <tr id="pipeline-{pipeline_id}">
                <td class="pipeline_index">{pipeline_id}</td>
                <td class="config_name">{pipeline_status['config_name']}</td>
                <td class="state">{pipeline_status['state']}</td>
                <td class="task_index">{pipeline_status['task_index']}/{pipeline_status['total_steps']}</td>
                <td class="start_time">{pipeline_status['start_time']}</td>
                <td class="end_time">{pipeline_status['end_time']}</td>
                <td class="duration">{pipeline_status['duration']}</td>
                <td class="current_task_name">{pipeline_status['current_task_name']}</td>
                <td class="details">{pipeline_status['details']}</td>
            </tr>
            """

        task_history_rows = ""
        for task_id, task_status in sorted_tasks_statuses:
            task_history_rows += f"""
            <tr id="task-{task_id}">
                <td class="pipeline_index">{task_status["pipeline_id"]}</td>
                <td class="task_name">{task_status['task_name']}</td>
                <td class="task_description">{task_status['task_description']}</td>
                <td class="task_state">{task_status['task_state']}</td>
                <td class="start_time">{task_status['start_time']}</td>
                <td class="end_time">{task_status['end_time']}</td>
                <td class="duration">{task_status['duration']}</td>
            </tr>
            """

        updated_html_content = html_template.replace("{pipeline_table_rows}", pipeline_table_rows)
        updated_html_content = updated_html_content.replace("{task_history_rows}", task_history_rows)

        if not os.path.exists(os.path.dirname(self.output_file)):
            os.makedirs(os.path.dirname(self.output_file))
            print(f"Folder created at: {os.path.dirname(self.output_file)}")
        # Replace the table body with new rows
        with open(self.output_file, "w") as f:
            f.write(updated_html_content)
