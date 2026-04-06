import json
import os

from app.domain.models import TaskInfo


class TaskStore:
    def __init__(self, root_dir: str, logger):
        self.root_dir = root_dir
        self.logger = logger

    def ensure_root(self):
        os.makedirs(self.root_dir, exist_ok=True)

    def task_dir(self, task_name: str) -> str:
        return os.path.join(self.root_dir, task_name)

    def meta_path(self, task_name: str) -> str:
        return os.path.join(self.task_dir(task_name), "meta.json")

    def save(self, task_name: str, data: dict):
        self.ensure_root()
        task_dir = self.task_dir(task_name)
        os.makedirs(task_dir, exist_ok=True)
        meta_path = self.meta_path(task_name)
        payload = json.dumps(data, indent=2, ensure_ascii=False)
        with open(meta_path, "w+", encoding="utf-8") as file:
            file.write(payload)
            file.flush()

    def load(self, task_name: str):
        meta_path = self.meta_path(task_name)
        if not os.path.exists(meta_path):
            return None
        with open(meta_path, encoding="utf-8") as file:
            return json.load(file)

    def load_task_info(self, task_dir: str):
        meta_path = os.path.join(task_dir, "meta.json")
        if not os.path.exists(meta_path):
            return None
        with open(meta_path, encoding="utf-8") as file:
            data = json.load(file)
        info = TaskInfo.from_dict(data)
        if info.video_url and os.path.exists(info.video_url):
            info.video_size = os.path.getsize(info.video_url)
        else:
            info.video_size = None
        return data, info
