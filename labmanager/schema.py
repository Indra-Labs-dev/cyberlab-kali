from pydantic import BaseModel


class LabDefinition(BaseModel):
    name: str
    display_name: str
    description: str = ""
    image: str
    internal_port: int


class LabInstance(BaseModel):
    id: str
    definition: str
    display_name: str
    status: str
    container_name: str
    host_port: int | None = None
    internal_port: int | None = None
    network: str | None = None
    created_at: str | None = None
