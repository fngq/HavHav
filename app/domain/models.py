from dataclasses import dataclass
from enum import Enum
from typing import Optional


class TaskStatus(str, Enum):
    Pending = "Pending"
    Running = "Running"
    Finished = "Finished"
    Failed = "Failed"
    Canceled = "Canceled"


@dataclass
class TaskInfo:
    name: str = ""
    url: str = ""
    title: str = ""
    status: TaskStatus = TaskStatus.Pending
    total: Optional[int] = None
    progress: Optional[int] = None
    start_time: Optional[int] = None
    finish_time: Optional[int] = None
    cover_url: Optional[str] = None
    cover: Optional[str] = None
    video_url: Optional[str] = None
    video_size: Optional[int] = None

    def to_dict(self) -> dict:
        return {key: value for key, value in self.__dict__.items() if value is not None}

    @classmethod
    def from_dict(cls, data: dict):
        valid_fields = set(cls.__init__.__code__.co_varnames[1:])
        filtered_data = {key: value for key, value in data.items() if key in valid_fields}
        if "status" in filtered_data:
            filtered_data["status"] = TaskStatus(filtered_data["status"])
        return cls(**filtered_data)


@dataclass
class DownloadInfo:
    m3u8_url: str = ""
    m3u8_file: str = ""
    m3u8_key_url: str = ""
    m3u8_key: str = ""
    m3u8_iv: str = ""
