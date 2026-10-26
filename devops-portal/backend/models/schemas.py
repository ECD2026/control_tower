from pydantic import BaseModel, Field
from typing import List, Optional


class DeploymentRequest(BaseModel):
    credential_id: Optional[str] = Field(
        default=None, description="Stored AWS credential to deploy with (Credentials page)"
    )
    provider: str = Field(default="aws", description="Cloud provider")
    region: str = Field(default="us-east-1", description="AWS region")
    instance_type: str = Field(default="t2.micro", description="EC2 instance type")
    instances: int = Field(default=1, ge=1, le=10, description="Number of instances")
    name: str = Field(
        default="",
        max_length=40,
        description="Optional friendly name; instances are tagged Name=<name>-<n>",
    )
    # Filled in by the deploy route from the selected credential; not user input.
    key_pair_name: str = Field(default="", description="Key pair name for SSH access")
    ssh_public_key: Optional[str] = Field(
        default=None, description="OpenSSH public key registered per deployment"
    )
    deployment_id: Optional[str] = Field(
        default=None, description="Portal deployment id, used to tag AWS resources"
    )
    detailed_monitoring: bool = Field(
        default=True,
        description="Enable 1-minute CloudWatch metrics (small extra AWS cost)",
    )
    security_group_ports: List[int] = Field(
        default=[22, 80, 443], description="Ports to open in security group"
    )
    os_type: str = Field(
        default="amazon_linux", description="OS type: amazon_linux or ubuntu"
    )
    packages: List[str] = Field(
        default=[], description="Packages to install (docker, nginx, etc.)"
    )
    custom_commands: str = Field(
        default="", description="Custom shell commands to run (one per line)"
    )
    docker_image: Optional[str] = Field(
        default="", description="Docker image to pull and run"
    )


class DeploymentResponse(BaseModel):
    deployment_id: str
    status: str
    work_dir: str
    execution_mode: str = "local"
    external_ref: Optional[str] = None
    external_url: Optional[str] = None


class DeploymentStatusResponse(BaseModel):
    deployment_id: str
    status: str
    execution_mode: Optional[str] = None
    external_ref: Optional[str] = None
    external_url: Optional[str] = None


class HistoryItem(BaseModel):
    id: str
    status: str
    execution_mode: str = "local"
    external_ref: Optional[str] = None
    external_url: Optional[str] = None
    provider: str
    region: str
    instance_type: str
    instances: int
    created_at: str
    updated_at: str
