# Backend image - also used for the cloudwatch-exporter service in
# docker-compose (same code, different command).
FROM python:3.12-slim

ENV LANG=C.UTF-8 LC_ALL=C.UTF-8

# Terraform (pinned) + OpenSSH client for Ansible's SSH connections.
ARG TERRAFORM_VERSION=1.8.5
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl unzip openssh-client ca-certificates && \
    curl -fsSL "https://releases.hashicorp.com/terraform/${TERRAFORM_VERSION}/terraform_${TERRAFORM_VERSION}_linux_amd64.zip" \
      -o terraform.zip && \
    unzip terraform.zip -d /usr/local/bin && \
    rm terraform.zip && \
    apt-get purge -y unzip && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*

# Ansible control node (full package: generated playbooks use community.docker)
RUN pip install --no-cache-dir ansible==10.1.0

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
