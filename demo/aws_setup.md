# AWS setup for the OptiServe demo

This guide builds the real AWS setup that OptiServe watches during the live demo:

- an Auto Scaling group `optiserve-demo` (t3.micro, min 1 / max 3 / desired 1), tagged `optiserve:managed=true`. Each instance runs the demo app and the agent.
- one idle instance on its own, `forgotten-test-box`, also tagged. OptiServe should suggest stopping it.
- an optional load balancer, so OptiServe can also read requests per minute.
- a billing alarm.
- full cleanup steps at the end.

Region: `ap-south-1` (Mumbai). Swap in your own region where needed. The commands use the AWS CLI v2. Every step can also be done in the console.

> **Cost:** t3.micro is free-tier eligible. Two to four instances for a few hours costs a few rupees. An ALB costs about $0.02 an hour while it exists. **Run the cleanup when you are done.**

```bash
export AWS_REGION=ap-south-1
export BACKEND_URL=https://your-optiserve-backend.example.com   # must be reachable from the instances
export AGENT_TOKEN=osa_xxx    # OptiServe → Settings → Agent tokens → New token ("demo-asg")
```

---

## 1. Give OptiServe access to AWS

Use **one** of these two options.

### Option A: IAM role (recommended when the backend runs on EC2)

```bash
aws iam create-role --role-name OptiServeBackend \
  --assume-role-policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"ec2.amazonaws.com"},"Action":"sts:AssumeRole"}]}'
aws iam put-role-policy --role-name OptiServeBackend --policy-name OptiServe \
  --policy-document file://demo/iam_policy.json
aws iam create-instance-profile --instance-profile-name OptiServeBackend
aws iam add-role-to-instance-profile --instance-profile-name OptiServeBackend --role-name OptiServeBackend
# Attach it to the backend's instance:
aws ec2 associate-iam-instance-profile --instance-id <backend-instance-id> \
  --iam-instance-profile Name=OptiServeBackend
```

In OptiServe's **Connect** page, pick the region and leave the key fields empty.

### Option B: IAM user with access keys (backend on your laptop or elsewhere)

```bash
aws iam create-user --user-name optiserve
aws iam put-user-policy --user-name optiserve --policy-name OptiServe \
  --policy-document file://demo/iam_policy.json
aws iam create-access-key --user-name optiserve   # copy AccessKeyId + SecretAccessKey once
```

Paste the keys into **Connect**. OptiServe keeps them only in the backend process's memory: they are never written to the database or logs, and a backend restart forgets them. To make them permanent, put `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` in `backend/.env`.

**What the policy allows** ([iam_policy.json](iam_policy.json)):
- read inventory and metrics everywhere;
- `SetDesiredCapacity`, `StopInstances` and `StartInstances` **only** on resources tagged `optiserve:managed=true`;
- an explicit deny on terminating instances or deleting groups.

---

## 2. Security group

```bash
VPC_ID=$(aws ec2 describe-vpcs --filters Name=is-default,Values=true --query 'Vpcs[0].VpcId' --output text)
SUBNETS=$(aws ec2 describe-subnets --filters Name=vpc-id,Values=$VPC_ID --query 'Subnets[0:2].SubnetId' --output text | tr '\t' ',')
SG_ID=$(aws ec2 create-security-group --group-name optiserve-demo --description "OptiServe demo" \
  --vpc-id $VPC_ID --query GroupId --output text)
aws ec2 authorize-security-group-ingress --group-id $SG_ID --protocol tcp --port 80 --cidr 0.0.0.0/0
```

The agent only makes outbound calls, so it needs no inbound rule.

---

## 3. Launch template (t3.micro + user-data)

The user-data runs once when each instance boots, including every instance the Auto Scaling group adds later, so a server added by an approved **scale up** joins OptiServe on its own:

1. **Demo app** ([demo_app/install.sh](demo_app/install.sh)): a systemd service on port 80. `GET /work?ms=50` burns real CPU on every core; `GET /metrics` returns `requests_per_min`.
2. **OptiServe agent** ([agent/install.sh](../agent/install.sh)): reports to `BACKEND_URL` every 10 s with the token, and reads the demo app's counter for requests per minute. Through IMDSv2 it links itself to its EC2 instance id. The template turns on **instance metadata tags**, so the agent can also read its Auto Scaling group name.

Save this as `user-data.sh`. Keep the two placeholders: `envsubst` below fills them in.

```bash
#!/bin/bash
# OptiServe demo instance: demo app on :80 + OptiServe agent. Log: /var/log/optiserve-user-data.log
set -euo pipefail
exec > >(tee -a /var/log/optiserve-user-data.log) 2>&1
BACKEND_URL="${BACKEND_URL}"
AGENT_TOKEN="${AGENT_TOKEN}"
SRC=/opt/optiserve-src

dnf install -y -q git
for attempt in 1 2 3 4 5; do
  rm -rf "$SRC"
  git clone --depth 1 --branch v2 https://github.com/Vishwas-shettyy/OptiServe.git "$SRC" && break
  echo "git clone failed (attempt $attempt), retrying in 10 s"; sleep 10
done

# 1. Demo app on port 80 (systemd service optiserve-demo-app)
bash "$SRC/demo/demo_app/install.sh" 80

# 2. Agent: every 10 s to the backend, with requests/min from the demo app's counter
bash "$SRC/agent/install.sh" "$BACKEND_URL" "$AGENT_TOKEN" http://127.0.0.1/metrics

echo "OptiServe demo instance ready: $(curl -fsS http://127.0.0.1/metrics)"
```

Check it on any instance with `sudo tail -n 30 /var/log/optiserve-user-data.log`, `systemctl status optiserve-demo-app optiserve-agent`, or `curl http://<public-ip>/metrics`. Within about 20 seconds of the agent starting, the instance shows up in OptiServe's live fleet.

```bash
envsubst '$BACKEND_URL $AGENT_TOKEN' < user-data.sh > user-data.rendered.sh
AMI=$(aws ssm get-parameter --name /aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64 \
  --query Parameter.Value --output text)
aws ec2 create-launch-template --launch-template-name optiserve-demo --launch-template-data "{
  \"ImageId\": \"$AMI\",
  \"InstanceType\": \"t3.micro\",
  \"SecurityGroupIds\": [\"$SG_ID\"],
  \"MetadataOptions\": {\"HttpTokens\": \"required\", \"InstanceMetadataTags\": \"enabled\"},
  \"UserData\": \"$(base64 < user-data.rendered.sh | tr -d '\n')\",
  \"TagSpecifications\": [{\"ResourceType\": \"instance\", \"Tags\": [{\"Key\": \"Name\", \"Value\": \"optiserve-demo\"}]}]
}"
```

> The agent token sits in the instance user-data, which anyone with `ec2:DescribeInstanceAttribute` can read. Use a token made only for the demo, and revoke it during cleanup.

---

## 4. (Optional) Load balancer, for requests per minute

```bash
TG_ARN=$(aws elbv2 create-target-group --name optiserve-demo-tg --protocol HTTP --port 80 --vpc-id $VPC_ID \
  --health-check-path / --query 'TargetGroups[0].TargetGroupArn' --output text)
LB_ARN=$(aws elbv2 create-load-balancer --name optiserve-demo-alb --type application \
  --subnets $(echo $SUBNETS | tr ',' ' ') --security-groups $SG_ID \
  --query 'LoadBalancers[0].LoadBalancerArn' --output text)
aws elbv2 create-listener --load-balancer-arn $LB_ARN --protocol HTTP --port 80 \
  --default-actions Type=forward,TargetGroupArn=$TG_ARN
aws elbv2 describe-load-balancers --load-balancer-arns $LB_ARN --query 'LoadBalancers[0].DNSName' --output text
```

If you skip the load balancer, OptiServe still gets requests per minute from the agent, which reads the demo app's counter.

---

## 5. Auto Scaling group `optiserve-demo`

```bash
aws autoscaling create-auto-scaling-group --auto-scaling-group-name optiserve-demo \
  --launch-template LaunchTemplateName=optiserve-demo,Version='$Latest' \
  --min-size 1 --max-size 3 --desired-capacity 1 \
  --vpc-zone-identifier "$SUBNETS" \
  ${TG_ARN:+--target-group-arns $TG_ARN} \
  --tags Key=optiserve:managed,Value=true,PropagateAtLaunch=true
```

Do **not** add scaling policies. OptiServe recommends changes and a person approves them.

---

## 6. The lone idle instance `forgotten-test-box`

```bash
aws ec2 run-instances --image-id $AMI --instance-type t3.micro --security-group-ids $SG_ID \
  --metadata-options HttpTokens=required \
  --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=forgotten-test-box},{Key=optiserve:managed,Value=true}]'
```

Leave it idle: it gets no user-data, so nothing runs on it. With `LIVE_MODE=true`, OptiServe flags it after about 10 quiet minutes.

---

## 7. Billing alarm (do this before anything else is left running)

Billing metrics exist only in `us-east-1`. First turn on **Billing preferences → Receive CloudWatch billing alerts** in the console, then:

```bash
TOPIC=$(aws sns create-topic --region us-east-1 --name optiserve-billing --query TopicArn --output text)
aws sns subscribe --region us-east-1 --topic-arn $TOPIC --protocol email --notification-endpoint you@example.com
aws cloudwatch put-metric-alarm --region us-east-1 --alarm-name optiserve-demo-billing \
  --namespace AWS/Billing --metric-name EstimatedCharges --dimensions Name=Currency,Value=USD \
  --statistic Maximum --period 21600 --evaluation-periods 1 --threshold 5 \
  --comparison-operator GreaterThanOrEqualToThreshold --alarm-actions $TOPIC
```

Confirm the subscription email. The alarm fires when the month's estimated bill reaches $5.

---

## 8. Connect and check

1. Start the backend with `LIVE_MODE=true` for the demo. Keep `DRY_RUN=true` until you have watched one dry run, then set it to `false`.
2. OptiServe → **Connect** → AWS → region `ap-south-1`. On first connect it backfills 14 days of hourly CloudWatch history.
3. **Servers** should show:
   - `optiserve-demo` with 1 server, merged with that instance's agent data (memory and disk appear);
   - `forgotten-test-box` as its own group.

---

## 9. Make load

From your laptop (Python 3.9+, `pip install httpx`), point [loadgen.py](loadgen.py) at the load balancer, or at the instance's public IP if you skipped it:

```bash
python demo/loadgen.py --url http://<alb-dns-name> --rps 30 --minutes 8
```

**Sizing:** each request burns `--work-ms` (default 50) of CPU, so one 2-vCPU t3.micro is full at about 40 requests/second. `--rps 30` puts a single instance at about 75% busy. That is enough for OptiServe to forecast a storm and suggest adding a server. After the second instance joins, the same load is about 40% per server. Use `--rps 60` for a harder spike: latency climbs as requests queue, and that is real too.

> t3 instances are burstable but launch in *unlimited* mode by default, so CPU is not throttled under load. A few minutes of load costs a few cents at most.

---

## 10. Cleanup (everything)

```bash
# Auto Scaling group and its instances
aws autoscaling delete-auto-scaling-group --auto-scaling-group-name optiserve-demo --force-delete
aws ec2 delete-launch-template --launch-template-name optiserve-demo
# Lone instance
aws ec2 terminate-instances --instance-ids $(aws ec2 describe-instances \
  --filters Name=tag:Name,Values=forgotten-test-box Name=instance-state-name,Values=pending,running,stopping,stopped \
  --query 'Reservations[].Instances[].InstanceId' --output text)
# Load balancer (if created)
aws elbv2 delete-load-balancer --load-balancer-arn $LB_ARN
aws elbv2 wait load-balancers-deleted --load-balancer-arns $LB_ARN
aws elbv2 delete-target-group --target-group-arn $TG_ARN
# Security group (after the instances are gone)
aws ec2 wait instance-terminated --filters Name=tag:Name,Values=optiserve-demo,forgotten-test-box
aws ec2 delete-security-group --group-id $SG_ID
# Access: Option B (user)
aws iam delete-access-key --user-name optiserve --access-key-id <AccessKeyId>
aws iam delete-user-policy --user-name optiserve --policy-name OptiServe
aws iam delete-user --user-name optiserve
# Access: Option A (role)
aws iam remove-role-from-instance-profile --instance-profile-name OptiServeBackend --role-name OptiServeBackend
aws iam delete-instance-profile --instance-profile-name OptiServeBackend
aws iam delete-role-policy --role-name OptiServeBackend --policy-name OptiServe
aws iam delete-role --role-name OptiServeBackend
# Billing alarm (optional: it is free to keep)
aws cloudwatch delete-alarms --region us-east-1 --alarm-names optiserve-demo-billing
aws sns delete-topic --region us-east-1 --topic-arn $TOPIC
```

Finally:
- revoke the demo agent token in OptiServe → Settings;
- in the EC2 console, check that no instances, load balancers or EBS volumes are left in the region.
