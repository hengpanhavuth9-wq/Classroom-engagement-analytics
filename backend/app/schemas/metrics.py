from pydantic import BaseModel
from datetime import datetime


class MetricRecordSchema(BaseModel):
    id:                int
    session_id:        str
    recorded_at:       datetime
    on_task_ratio:     float
    class_engagement:  float
    student_count:     int
    tracked_count:     int
    engaged_count:     int
    below_floor_count: int
    on_task_count:     int
    desk_work_count:   int
    off_task_count:    int
    unknown_count:     int

    class Config:
        from_attributes = True
