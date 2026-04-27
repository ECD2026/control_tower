## AWS ORGANISATIONAL UNIT CONTROL TOWER
DevOps Automation Portal with Jenkins, Terraform, Ansible & Monitoring

# Project Overview

AWS Organisational Unit Control Tower is a DevOps Automation Portal designed to automate the lifecycle of cloud infrastructure—from provisioning to configuration, management, and monitoring.

The system integrates industry-standard tools to provide a centralized platform for managing AWS resources efficiently using DevOps practices.

# Objectives
Automate infrastructure provisioning using Infrastructure as Code
Enable seamless configuration of instances
Provide centralized control over multiple AWS resources
Support Day-2 operations (post-deployment management)
Integrate monitoring for real-time system insights
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

# Tech Stack
Category	Tools Used
Frontend	React (Vite)
Backend	FastAPI (Python)
CI/CD	Jenkins
Infrastructure	Terraform
Configuration	Ansible
Cloud	AWS EC2
Monitoring	Prometheus & Grafana
Containerization	Docker
Orchestration Kubernetes

# Features
- 1. Automated Deployment
One-click infrastructure creation
Uses Terraform for AWS provisioning
Supports multiple configurations
- 2. Configuration Management
Ansible automates:
Package installation
Software setup
Custom commands
- 3. Jenkins Integration
Backend triggers Jenkins pipelines
Secure and scalable execution
Real-time logs streaming
- 4. Instance Management (Day-2 Operations)
View all deployed instances
Install additional packages anytime
Apply updates without redeployment
- 5. Monitoring System
Prometheus collects metrics
Grafana visualizes:
CPU usage
Memory usage
Network stats
- 6. Docker & Kubernetes Support
Deploy containerized applications
Optional Kubernetes orchestration

# How It Works
User submits deployment request via UI
Backend validates and sends request to Jenkins
Jenkins pipeline executes:
Terraform → creates AWS infrastructure
Ansible → configures instances
Instance details are stored in database
User can manage instances later (Day-2 ops)
Monitoring tools track performance in real-time

# Security Features
Separation of execution via Jenkins
Secure credential handling (AWS keys, SSH keys)
Controlled network access via AWS Security Groups
Restricted monitoring ports
Logging and traceability through pipelines

# Future Enhancements
Integrate security tools (Trivy, SonarQube)
Add Role-Based Access Control (RBAC)
Use AWS Control Tower for real OU management
Implement CI/CD pipelines for application deployment
Add multi-cloud support

# Conclusion

This project demonstrates how multiple DevOps tools can be integrated into a single automation platform to simplify cloud infrastructure management, improve efficiency, and enable scalability.
🧾 Conclusion

This project demonstrates how multiple DevOps tools can be integrated into a single automation platform to simplify cloud infrastructure management, improve efficiency, and enable scalability.
