# 🚀 FICO AWS Account Automation Platform

## 📌 Overview

This project implements an **end-to-end DevOps automation platform** for provisioning and managing AWS infrastructure using **Terraform, Jenkins, Docker, and IAM**.

The system simulates a **real-world enterprise environment** where multiple developers collaborate using Git, while infrastructure is provisioned securely and consistently through CI/CD pipelines.

---

## 🎯 Objectives

* Automate AWS infrastructure provisioning using **Infrastructure as Code (IaC)**
* Enable **multi-developer collaboration** with Git branching strategies
* Implement **secure IAM role-based access control**
* Build a **CI/CD pipeline using Jenkins (Dockerized)**
* Ensure **scalable, reproducible, and version-controlled infrastructure**

---

## 🏗️ Architecture Overview

```
Developer → GitHub → Jenkins (Docker)
          → Terraform → AWS
          → S3 (State Storage)
          → DynamoDB (State Locking)
```

---

## 🧰 Tech Stack

| Category         | Technology       |
| ---------------- | ---------------- |
| Version Control  | GitHub           |
| CI/CD            | Jenkins (Docker) |
| Infrastructure   | Terraform        |
| Cloud Provider   | AWS              |
| Containerization | Docker           |
| State Management | S3 + DynamoDB    |
| Authentication   | IAM Roles        |

---

## 📁 Project Structure

```
project-root/
│
├── terraform/
│   ├── modules/
│   │   ├── network/
│   │   ├── ec2/
│   │   ├── iam/
│   │
│   ├── environments/
│   │   ├── dev/
│   │   ├── test/
│   │   ├── prod/
│
├── jenkins/
│   └── Jenkinsfile
│
├── docker/
│   └── Dockerfile
│
└── README.md
```

---

## 🌿 Git Branching Strategy

### Branches

* `main` → Production-ready code (default branch)
* `feature-1` → Developer 1
* `feature-2` → Developer 2
* `feature-3` → Developer 3

### Workflow

1. Each developer works on their own feature branch
2. Regularly sync with `main`
3. Create Pull Request → `main`
4. Merge after review

---

## 🔐 AWS Setup

### IAM Components

* **IAM User:** `platform-admin`

  * Used for initial setup only
* **IAM Role:** `githubterraform`

  * Used by Terraform/Jenkins to provision infrastructure

---

### Terraform Backend

#### S3 Bucket

* Stores Terraform state
* Versioning enabled

#### DynamoDB Table

* Handles state locking
* Prevents concurrent modifications

---

## ⚙️ Setup Instructions

---

### 1️⃣ Clone Repository

```bash
git clone https://github.com/your-repo.git
cd your-repo
```

---

### 2️⃣ Configure AWS CLI

```bash
aws configure
```

Enter:

* Access Key
* Secret Key
* Region (e.g., ap-south-1)

---

### 3️⃣ Initialize Terraform

```bash
terraform init
```

---

### 4️⃣ Validate Terraform

```bash
terraform validate
```

---

### 5️⃣ Plan Infrastructure

```bash
terraform plan
```

---

### 6️⃣ Apply Infrastructure

```bash
terraform apply
```

---

## 🐳 Jenkins Setup (Docker)

### Build Jenkins Image

```bash
docker build -t jenkins-terraform .
```

---

### Run Jenkins Container

```bash
docker run -p 8080:8080 jenkins-terraform
```

---

### Jenkins Configuration

Install plugins:

* Git Plugin
* Pipeline Plugin
* AWS Credentials Plugin
* Terraform Plugin

---

## 🔄 CI/CD Pipeline

### Pipeline Stages

1. Checkout Code
2. Terraform Init
3. Terraform Validate
4. Terraform Plan
5. (Future) Terraform Apply

---

## 🔒 Security Best Practices

* ❌ No hardcoded credentials
* ✅ Use IAM roles instead of users
* ✅ Enable S3 encryption
* ✅ Use least privilege policies
* ✅ Protect `main` branch with PR rules

---

## 📊 Features Implemented

* Modular Terraform architecture
* Remote backend with locking
* Multi-developer Git workflow
* Dockerized Jenkins setup
* Secure IAM-based access

---

## 🚧 Future Enhancements

* GitHub Actions integration
* Kubernetes-based Jenkins scaling
* Monitoring with CloudWatch / Prometheus
* Multi-region disaster recovery
* Automated approval workflows

---

## 🧠 Key Learnings

* Infrastructure as Code (IaC)
* CI/CD pipeline design
* Git collaboration workflows
* AWS IAM security practices
* Terraform state management

---

## 👨‍💻 Contributors

* Developer 1 → Feature 1
* Developer 2 → Feature 2
* Developer 3 → Feature 3

---

## 📜 License

This project is for educational and demonstration purposes.

---

## ⭐ Final Note

This project demonstrates a **production-style DevOps pipeline** with real-world tools and practices. It is designed to simulate enterprise-level infrastructure automation and team collaboration.

---

🚀 *Built for learning, designed like production.*
