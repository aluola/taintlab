from typing import Annotated, Literal, Union
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid')

class SearchArgs(Strict):
    query: str = Field(min_length=1, max_length=12000)

class ReadArgs(Strict):
    doc_id: str = Field(min_length=1, max_length=512)

class NotifyArgs(Strict):
    recipient_id: str = Field(min_length=1, max_length=512)
    body: str = Field(min_length=1, max_length=12000)

class ExportArgs(Strict):
    path: str = Field(min_length=1, max_length=512)
    content: str = Field(min_length=1, max_length=12000)

class Search(Strict):
    type: Literal['tool_call']
    tool: Literal['search_info']
    arguments: SearchArgs

class Read(Strict):
    type: Literal['tool_call']
    tool: Literal['read_document']
    arguments: ReadArgs

class Notify(Strict):
    type: Literal['tool_call']
    tool: Literal['send_notification']
    arguments: NotifyArgs

class Export(Strict):
    type: Literal['tool_call']
    tool: Literal['export_file']
    arguments: ExportArgs

class Final(Strict):
    type: Literal['final']
    content: str = Field(min_length=1, max_length=12000)

Action = Union[Search, Read, Notify, Export, Final]
ACTION = TypeAdapter(Action)
ACTION_SCHEMA = ACTION.json_schema()

def parse_action(raw: str) -> dict:
    # No arbitrary code evaluation, no natural-language claims as execution evidence.
    return ACTION.validate_json(raw).model_dump()
