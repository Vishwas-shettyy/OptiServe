"""The only AWS write calls OptiServe makes: set ASG desired capacity and stop an instance. Never terminate."""

from dataclasses import dataclass
from typing import Optional

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from app.connectors.aws import AwsError, _is_managed, _tags, friendly_error


@dataclass
class CapacityStatus:
    """An Auto Scaling group's size right now."""

    desired: int
    in_service: int
    min_size: int
    max_size: int
    managed: bool


def _asg(session: boto3.Session, asg_name: str) -> dict:
    """Describe one Auto Scaling group or raise AwsError."""
    try:
        groups = session.client("autoscaling").describe_auto_scaling_groups(AutoScalingGroupNames=[asg_name])
    except (ClientError, BotoCoreError) as exc:
        raise AwsError(friendly_error(exc)) from exc
    found = groups.get("AutoScalingGroups", [])
    if not found:
        raise AwsError(f"The Auto Scaling group {asg_name} no longer exists.")
    return found[0]


def capacity_status(session: boto3.Session, asg_name: str) -> CapacityStatus:
    """Return desired size, in-service instances, limits and the managed tag of an ASG."""
    g = _asg(session, asg_name)
    in_service = sum(1 for i in g.get("Instances", []) if i.get("LifecycleState") == "InService")
    return CapacityStatus(g["DesiredCapacity"], in_service, g["MinSize"], g["MaxSize"], _is_managed(_tags(g.get("Tags"))))


def set_desired_capacity(session: boto3.Session, asg_name: str, desired: int) -> CapacityStatus:
    """Call autoscaling:SetDesiredCapacity after checking the managed tag and min/max; return the status before."""
    before = capacity_status(session, asg_name)
    if not before.managed:
        raise AwsError(f"{asg_name} is not tagged optiserve:managed=true, so OptiServe will not change it.")
    if not before.min_size <= desired <= before.max_size:
        raise AwsError(f"{desired} servers is outside {asg_name}'s limits ({before.min_size}–{before.max_size}).")
    try:
        session.client("autoscaling").set_desired_capacity(
            AutoScalingGroupName=asg_name, DesiredCapacity=desired, HonorCooldown=False
        )
    except (ClientError, BotoCoreError) as exc:
        raise AwsError(friendly_error(exc)) from exc
    return before


def instance_state(session: boto3.Session, instance_id: str) -> tuple[str, bool]:
    """Return (EC2 state name, managed tag) for one instance."""
    try:
        res = session.client("ec2").describe_instances(InstanceIds=[instance_id])
    except (ClientError, BotoCoreError) as exc:
        raise AwsError(friendly_error(exc)) from exc
    for reservation in res.get("Reservations", []):
        for inst in reservation.get("Instances", []):
            return inst.get("State", {}).get("Name", "unknown"), _is_managed(_tags(inst.get("Tags")))
    raise AwsError(f"Instance {instance_id} no longer exists.")


def stop_instance(session: boto3.Session, instance_id: str, asg_name: Optional[str] = None) -> None:
    """Stop (never terminate) one managed instance; an ASG member is first moved to standby so it is not replaced."""
    state, managed = instance_state(session, instance_id)
    if not managed:
        raise AwsError(f"{instance_id} is not tagged optiserve:managed=true, so OptiServe will not stop it.")
    if state in ("stopping", "stopped"):
        return
    try:
        if asg_name:
            session.client("autoscaling").enter_standby(
                InstanceIds=[instance_id], AutoScalingGroupName=asg_name, ShouldDecrementDesiredCapacity=True
            )
        session.client("ec2").stop_instances(InstanceIds=[instance_id])
    except (ClientError, BotoCoreError) as exc:
        raise AwsError(friendly_error(exc)) from exc
