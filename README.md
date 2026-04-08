## AWS Organizational Unit Control Tower
(DevOps Automation Portal)

# Overview

This project implements an end-to-end DevOps Automation Portal that enables users to provision and manage AWS infrastructure through a web-based interface.

The system integrates Terraform, Ansible, and FastAPI to automate infrastructure provisioning, server configuration, and deployment, simulating a real-world enterprise DevOps environment with minimal manual intervention.

# Objectives
Automate infrastructure provisioning using Infrastructure as Code (IaC)
Provide a self-service web portal for DevOps operations
Enable dynamic generation of Terraform and Ansible configurations
Ensure secure and scalable deployments on AWS
Provide real-time logs and deployment status tracking

# System Architecture
<img width="2662" height="1088" alt="image" src="https://github.com/user-attachments/assets/64f84a4c-7b90-43a7-ad1a-8

# STEP 1:- User fills form:

Cloud provider, region, instance type
Packages (Docker, Nginx, etc.)
Deployment preferences (Kubernetes, replicas)

# STEP 2:- API Request

Frontend sends:

POST /deploy

With JSON payload to FastAPI

# STEP 3:- Backend Processing
Generates:
Terraform configuration (main.tf)
Ansible playbook (setup.yml)
Stores files temporarily

# STEP 4:- Infrastructure Provisioning
terraform init
terraform apply

👉 Creates EC2 instances on AWS

# STEP 5:- Configuration Management
ansible-playbook setup.yml

👉 Installs packages and configures servers

# STEP 6:- Deployment
Docker container setup OR
Kubernetes deployment (if selected)

# STEP 7:-Monitoring & Logs
Logs streamed to frontend in real-time
Status shown:
Pending
Running
Success
Failed
# Security Best Practices
❌ No hardcoded credentials
✅ Use environment variables for AWS access
✅ IAM role-based access control
✅ Secure API handling
✅ Temporary file storage

# Future Enhancements
Deployment history tracking
Multi-cloud support (GCP, Azure)
Kubernetes auto-scaling
Role-based user authentication
Advanced monitoring dashboards
