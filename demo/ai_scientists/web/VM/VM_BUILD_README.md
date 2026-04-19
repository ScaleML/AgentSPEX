# Building the AI Scientist VM Image

This guide covers how to create a distributable `.utm` virtual machine image for the OptimalScale AI Scientist Web UI on a Mac with Apple Silicon.

---

## Prerequisites

- **Mac with Apple Silicon** (M1/M2/M3/M4)
- **UTM** — Free VM manager. Install via `brew install --cask utm` or download from https://mac.getutm.app/
- **Ubuntu 22.04 ARM Server ISO** — Download:
  ```bash
  curl -LO https://cdimage.ubuntu.com/releases/22.04/release/ubuntu-22.04.5-live-server-arm64.iso
  ```

---

## Step 1: Create the VM in UTM

1. Open **UTM** → click **"+"** → **Virtualize** → **Linux**
2. Configure:
   - **Boot ISO Image**: select `ubuntu-22.04.5-live-server-arm64.iso`
   - **Memory**: 8192 MB
   - **CPU Cores**: 4
   - **Storage**: 64 GB
   - **Name**: `AI-Scientists`
3. Click **Save**

### Configure Port Forwarding

1. Right-click `AI-Scientists` VM → **Edit**
2. Select **Network** on the left
3. Network Mode: **Emulated VLAN**
4. Expand **Port Forward**, add 3 rules:

| Protocol | Guest Port | Host Port |
|----------|-----------|-----------|
| TCP      | 5001      | 15001     |
| TCP      | 6080      | 6080      |
| TCP      | 22        | 2222      |

5. Click **Save**

---

## Step 2: Install Ubuntu

1. Start the VM in UTM
2. Follow the Ubuntu installer:
   - Language: **English**
   - Keyboard: **English (US)**
   - Install type: **Ubuntu Server**
   - Network: keep default (DHCP)
   - Proxy: leave empty
   - Mirror: keep default
   - Storage: **Use an entire disk** → confirm
   - Profile:
     - Name: `aiscientist`
     - Server name: `ai-scientists`
     - Username: `aiscientist`
     - Password: `aiscientist`
   - SSH: **check** "Install OpenSSH server"
   - Featured Snaps: select nothing, click Done
3. Wait for installation to complete (~5-10 minutes)
4. When you see "Reboot Now": eject the ISO in UTM first, then reboot

### Enable SSH Password Authentication

After reboot, log in at the UTM console (username: `aiscientist`, password: `aiscientist`):

```bash
sudo sed -i 's/^#*PasswordAuthentication.*/PasswordAuthentication yes/' /etc/ssh/sshd_config
sudo sed -i 's/^#*KbdInteractiveAuthentication.*/KbdInteractiveAuthentication yes/' /etc/ssh/sshd_config
sudo systemctl restart sshd
```

### Verify SSH from Mac

```bash
ssh -p 2222 aiscientist@localhost
# Password: aiscientist
```

---

## Step 3: Transfer Project Code

### On the remote server (where the code lives)

```bash
cd /home/exouser
tar czf /tmp/controllable-sandbox.tar.gz \
    --exclude='controllable-sandbox/workspace' \
    --exclude='controllable-sandbox/workspace_persistent' \
    --exclude='controllable-sandbox/outputs' \
    --exclude='controllable-sandbox/.git' \
    controllable-sandbox/
```

### On your Mac

```bash
# Download from remote server to Mac
scp <user>@<server-ip>:/tmp/controllable-sandbox.tar.gz ~/Downloads/

# Upload from Mac to VM
scp -P 2222 ~/Downloads/controllable-sandbox.tar.gz aiscientist@localhost:~/
```

### Inside the VM

```bash
ssh -p 2222 aiscientist@localhost
tar xzf ~/controllable-sandbox.tar.gz -C ~/
rm ~/controllable-sandbox.tar.gz
```

---

## Step 4: Accept Conda ToS (if needed)

If Conda prompts for Terms of Service acceptance:

```bash
sudo -u aiscientist /home/aiscientist/miniconda3/bin/conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/main
sudo -u aiscientist /home/aiscientist/miniconda3/bin/conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/r
```

---

## Step 5: Run install.sh

```bash
ssh -p 2222 aiscientist@localhost
cd ~/controllable-sandbox
sudo bash demo/ai_scientists/install.sh
```

This takes ~30-40 minutes. The script will:
1. Install system packages, Docker, Conda, LaTeX
2. Create the `yaml_agent` Python environment with all dependencies
3. Build the Docker sandbox image
4. Configure systemd services for auto-start on boot
5. Install the first-boot API key setup portal

When complete, open `http://localhost:15001` in your Mac browser to verify the setup portal appears.

---

## Step 6: Test the Website

1. Enter your OpenAI API Key on the setup page
2. Click **Save & Start**
3. Wait ~60 seconds for services to start
4. Refresh the page — you should see the AI Scientist chat interface
5. Try generating a proposal to verify everything works

---

## Step 7: Clean Private Data Before Distribution

SSH into the VM and run:

```bash
ssh -p 2222 aiscientist@localhost

# Clear API keys
sed -i 's|^OPENAI_API_KEY=.*|OPENAI_API_KEY=|' ~/controllable-sandbox/config/vm.env
sed -i 's|^FIRECRAWL_API_KEY=.*|FIRECRAWL_API_KEY=|' ~/controllable-sandbox/config/vm.env

# Delete SSH keys
rm -rf ~/.ssh && mkdir ~/.ssh && chmod 700 ~/.ssh

# Remove setup sentinel (so new users see the setup page)
rm -f ~/.setup-complete

# Delete run outputs and workspace
sudo rm -rf ~/controllable-sandbox/outputs/*
sudo rm -rf ~/controllable-sandbox/workspace/*
sudo rm -rf ~/controllable-sandbox/workspace_persistent/*

# Delete misc files
rm -f ~/.sudo_as_admin_successful
rm -rf ~/.cache

# Clear shell history
history -c
> ~/.bash_history

# Shut down
sudo shutdown now
```

---

## Step 8: Distribute the .utm File

1. After the VM shuts down, find the `.utm` file:
   ```bash
   ls ~/Library/Containers/com.utmapp.UTM/Data/Documents/
   ```
2. Copy the `.utm` file to your distribution location
3. Share it with users — they double-click to import into UTM

> **Note**: Each `.utm` copy is an independent VM. Users' changes do not affect the original.
