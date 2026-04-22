FROM python:3.12-slim

# Install Terraform
RUN apt-get update && apt-get install -y curl unzip gnupg && \
    curl -fsSL https://releases.hashicorp.com/terraform/1.8.5/terraform_1.8.5_linux_amd64.zip \
      -o terraform.zip && \
    unzip terraform.zip -d /usr/local/bin && \
    rm terraform.zip

# Install Ansible
RUN pip install --no-cache-dir ansible

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
