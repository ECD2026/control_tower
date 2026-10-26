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

Frontend (UI)
↓
Backend (FastAPI)
↓
Jenkins (Execution Engine)
↓
Terraform (Infrastructure Provisioning)
↓
AWS EC2 (Cloud Resources)
↓
Ansible (Configuration Management)
↓
Monitoring (Prometheus + Grafana)

Tech Stack

Frontend: React (Vite)
Backend: FastAPI (Python)
CI/CD: Jenkins
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
3. Jenkins Integration
Backend triggers Jenkins pipelines
Ensures secure and controlled execution
Provides real-time log streaming
4. Instance Management (Day-2 Operations)
View and manage deployed instances
Install additional packages anytime
Update systems without redeployment
5. Monitoring System
Prometheus collects system metrics
Grafana visualizes CPU, memory, and network performance
6. Docker & Kubernetes Support
Supports containerized application deployment
Optional Kubernetes orchestration for scaling and management

# How It Works
User submits a deployment request through the UI
Backend validates the request and triggers Jenkins
Jenkins pipeline executes:
Terraform → provisions AWS infrastructure
Ansible → configures instances
Deployment logs are streamed to the frontend
Instance details are stored for future management
Users can perform Day-2 operations
Monitoring tools track system performance
Security Features
Separation of execution using Jenkins
Secure handling of AWS credentials and SSH keys
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
├── jenkins/
├── monitoring/
├── docker-compose.yml
└── docs/

# Future Enhancements
Integrate security tools like Trivy and SonarQube
Implement Role-Based Access Control (RBAC)
Extend support to AWS Control Tower for real OU management
Add advanced CI/CD pipelines for application deployment
Enable multi-cloud support
Conclusion
Provides a centralized platform for DevOps automation
Reduces manual effort and configuration errors
Enables scalable and efficient infrastructure management
Integrates provisioning, configuration, and monitoring in one system
Demonstrates practical implementation of DevOps tools and practices
