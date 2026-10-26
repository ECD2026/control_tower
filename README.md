## AWS ORGANISATIONAL UNIT CONTROL TOWER

# DevOps Automation Portal

# Project Overview

AWS Organisational Unit Control Tower is a DevOps Automation Portal designed to automate the complete lifecycle of cloud infrastructure — from provisioning and configuration to management and monitoring.

The platform integrates multiple DevOps tools to provide a centralized, efficient, and scalable solution for managing AWS resources.

# Objectives
Automate infrastructure provisioning using Infrastructure as Code
Enable seamless and automated configuration of instances
Provide centralized control over cloud resources
Support Day-2 operations (post-deployment management)
Integrate monitoring for real-time insights
Improve scalability, reliability, and efficiency

# Architecture Overview

Frontend (React UI, login, per-user AWS credentials)
↓
Backend (FastAPI)
↓
GitHub Actions (Execution Engine — portal-deploy.yml)
↓
Terraform (Infrastructure Provisioning)
↓
AWS EC2 (Cloud Resources)
↓
Ansible (Configuration Management)
↓
Monitoring (CloudWatch exporter → Prometheus → Grafana)

Full details, diagrams and the security model: [docs/architecture.md](docs/architecture.md).

Tech Stack

Frontend: React (Vite)
Backend: FastAPI (Python)
CI/CD: GitHub Actions
Infrastructure: Terraform
Configuration: Ansible
Cloud: AWS EC2
Monitoring: Prometheus & Grafana
Containerization: Docker
Orchestration: Kubernetes 

# Features
1. Automated Deployment
One-click infrastructure provisioning
Uses Terraform for AWS resource creation
Supports multiple configurations
2. Configuration Management
Automates server setup using Ansible
Installs required packages and dependencies
Executes custom commands
3. GitHub Actions Integration
Backend dispatches the portal-deploy.yml workflow
The user's AWS keys and SSH key travel encrypted and are masked in logs
Provides real-time log streaming and a link to the run
4. Instance Management (Day-2 Operations)
View and manage deployed instances
Pause, resume, restart and terminate instances
Install additional packages anytime
Update systems without redeployment
5. Monitoring System
A multi-account CloudWatch exporter feeds Prometheus for every instance
node_exporter adds memory and disk metrics when installed
Grafana dashboards are embedded in the portal, behind its login
6. Docker & Kubernetes Support
Supports containerized application deployment
Optional Kubernetes orchestration for scaling and management

# How It Works
User signs in and uploads AWS access keys + an SSH key pair (verified with STS, encrypted at rest)
User submits a deployment request through the UI
Backend validates the request and dispatches the GitHub Actions workflow
The workflow executes:
Terraform → provisions AWS infrastructure
Ansible → configures instances
Deployment logs are streamed to the frontend
Instance details are stored for future management
Users can perform Day-2 operations
Monitoring tools track system performance
Security Features
Per-user accounts; every resource and action is scoped to its owner
Separation of execution using GitHub Actions
AWS credentials and SSH keys encrypted at rest and in transit to the runner
Monitoring UIs only reachable after login
Controlled access via AWS Security Groups
Restricted monitoring ports
Logging and traceability of all operations

# Project Structure

devops-portal/
│
├── frontend/
├── backend/
│ ├── routes/
│ ├── services/
│ ├── generators/
│ └── database/
│
├── exporters/          (CloudWatch exporter, inside backend/)
├── infra/              (Terraform + scripts for the portal host)
├── monitoring/
├── docker-compose.yml
└── docs/               (architecture.md, demo-runbook.md)

.github/workflows/
├── portal-deploy.yml   (Terraform + Ansible per deployment)
└── portal-release.yml  (test + release the portal to AWS)

# Getting Started
Hosting on AWS and the demo walkthrough: [docs/demo-runbook.md](docs/demo-runbook.md).
Local: `cd devops-portal && docker compose up -d --build`, then open http://localhost.

# Future Enhancements
Integrate security tools like Trivy and SonarQube
Extend user accounts with Role-Based Access Control (RBAC)
Extend support to AWS Control Tower for real OU management
Add advanced CI/CD pipelines for application deployment
Enable multi-cloud support
Conclusion
Provides a centralized platform for DevOps automation
Reduces manual effort and configuration errors
Enables scalable and efficient infrastructure management
Integrates provisioning, configuration, and monitoring in one system
Demonstrates practical implementation of DevOps tools and practices
