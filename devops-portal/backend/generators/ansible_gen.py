"""
Dynamically generates an Ansible playbook based on user input.
"""


def generate_ansible(request) -> str:
    is_ubuntu = request.os_type == "ubuntu"
    pkg_mgr = "apt" if is_ubuntu else "yum"
    ssh_user = "ubuntu" if is_ubuntu else "ec2-user"

    tasks: list[str] = []

    # ── System update ────────────────────────────────────────────────────────
    if is_ubuntu:
        tasks.append("""\
    - name: Update apt cache
      apt:
        update_cache: yes
        cache_valid_time: 3600""")
    else:
        tasks.append("""\
    - name: Update yum cache
      yum:
        name: "*"
        state: latest
        update_cache: yes""")

    # ── Common packages ──────────────────────────────────────────────────────
    for pkg in request.packages:
        pkg_lower = pkg.lower()

        if pkg_lower == "docker":
            if is_ubuntu:
                tasks.append("""\
    - name: Install Docker prerequisites
      apt:
        name:
          - apt-transport-https
          - ca-certificates
          - curl
          - gnupg
          - software-properties-common
        state: present

    - name: Add Docker GPG key
      apt_key:
        url: https://download.docker.com/linux/ubuntu/gpg
        state: present

    - name: Add Docker repository
      apt_repository:
        repo: "deb [arch=amd64] https://download.docker.com/linux/ubuntu focal stable"
        state: present

    - name: Install Docker CE
      apt:
        name:
          - docker-ce
          - docker-ce-cli
          - containerd.io
        state: present
        update_cache: yes

    - name: Start and enable Docker
      service:
        name: docker
        state: started
        enabled: yes

    - name: Add user to docker group
      user:
        name: "{{ ansible_user }}"
        groups: docker
        append: yes""")
            else:
                tasks.append("""\
    - name: Install Docker
      yum:
        name: docker
        state: present

    - name: Start and enable Docker
      service:
        name: docker
        state: started
        enabled: yes

    - name: Add user to docker group
      user:
        name: "{{ ansible_user }}"
        groups: docker
        append: yes""")

        elif pkg_lower in ("kubernetes", "k3s", "k8s"):
            tasks.append("""\
    - name: Install k3s (lightweight Kubernetes)
      shell: |
        curl -sfL https://get.k3s.io | sh -
      args:
        creates: /usr/local/bin/k3s
        executable: /bin/bash

    - name: Wait for k3s to be ready
      shell: k3s kubectl get nodes
      retries: 10
      delay: 10
      register: k3s_ready
      until: k3s_ready.rc == 0""")

        elif pkg_lower == "nginx":
            tasks.append(f"""\
    - name: Install Nginx
      {pkg_mgr}:
        name: nginx
        state: present

    - name: Start and enable Nginx
      service:
        name: nginx
        state: started
        enabled: yes""")

        elif pkg_lower == "git":
            tasks.append(f"""\
    - name: Install Git
      {pkg_mgr}:
        name: git
        state: present""")

        elif pkg_lower in ("python3", "python"):
            tasks.append(f"""\
    - name: Install Python3 and pip
      {pkg_mgr}:
        name:
          - python3
          - python3-pip
        state: present""")

        elif pkg_lower == "nodejs":
            if is_ubuntu:
                tasks.append("""\
    - name: Add NodeJS repository
      shell: curl -fsSL https://deb.nodesource.com/setup_18.x | bash -
      args:
        executable: /bin/bash

    - name: Install NodeJS
      apt:
        name: nodejs
        state: present
        update_cache: yes""")
            else:
                tasks.append("""\
    - name: Install NodeJS
      shell: |
        curl -fsSL https://rpm.nodesource.com/setup_18.x | bash -
        yum install -y nodejs
      args:
        executable: /bin/bash""")

        else:
            tasks.append(f"""\
    - name: Install {pkg}
      {pkg_mgr}:
        name: {pkg_lower}
        state: present""")

    # ── Docker container deployment ──────────────────────────────────────────
    if request.docker_image and request.docker_image.strip():
        image = request.docker_image.strip()
        tasks.append(f"""\
    - name: Pull Docker image {image}
      community.docker.docker_image:
        name: {image}
        source: pull

    - name: Run Docker container
      community.docker.docker_container:
        name: devops-app
        image: {image}
        state: started
        restart_policy: always
        published_ports:
          - "80:80" """)

    # ── Kubernetes deployment ────────────────────────────────────────────────
    if request.kubernetes and request.docker_image and request.docker_image.strip():
        image = request.docker_image.strip()
        replicas = request.replicas
        tasks.append(f"""\
    - name: Deploy application to Kubernetes
      shell: |
        k3s kubectl create deployment devops-app \\
          --image={image} \\
          --replicas={replicas} \\
          --dry-run=client -o yaml | k3s kubectl apply -f -
        k3s kubectl expose deployment devops-app \\
          --type=NodePort --port=80 \\
          --dry-run=client -o yaml | k3s kubectl apply -f -
      args:
        executable: /bin/bash

    - name: Wait for Kubernetes deployment
      shell: k3s kubectl rollout status deployment/devops-app --timeout=120s
      args:
        executable: /bin/bash""")

    # ── Custom commands ──────────────────────────────────────────────────────
    if request.custom_commands and request.custom_commands.strip():
        for idx, cmd in enumerate(request.custom_commands.strip().splitlines(), start=1):
            cmd = cmd.strip()
            if cmd:
                tasks.append(f"""\
    - name: "Custom command {idx}: {cmd[:60]}"
      shell: {cmd}
      args:
        executable: /bin/bash""")

    tasks.append("""\
    - name: Deployment complete
      debug:
        msg: "All tasks completed successfully on {{ inventory_hostname }}!" """)

    tasks_yaml = "\n\n".join(tasks)

    playbook = f"""---
# ============================================================
# Generated by DevOps Automation Portal
# OS Type  : {request.os_type}
# Packages : {", ".join(request.packages) if request.packages else "none"}
# ============================================================

- name: Configure DevOps Portal Servers
  hosts: servers
  become: yes
  gather_facts: yes
  vars:
    ansible_user: {ssh_user}

  tasks:
{tasks_yaml}
"""
    return playbook
