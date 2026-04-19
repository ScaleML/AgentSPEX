# Building the AI Scientist VM on Windows

This guide covers how to create the OptimalScale AI Scientist Web UI virtual machine on a Windows PC using VirtualBox.

---

## Prerequisites

- **Windows 10/11** (64-bit)
- **VirtualBox 7.0+** — Download from https://www.virtualbox.org/wiki/Downloads
- **Ubuntu 22.04 Server ISO** — Download:
  ```
  https://releases.ubuntu.com/22.04.5/ubuntu-22.04.5-live-server-amd64.iso
  ```
- **16 GB RAM** recommended (8 GB minimum)
- **70 GB** free disk space

---

## Step 1: Create the VM in VirtualBox

1. Open VirtualBox → click **New**
2. Configure:
   - **Name**: `OptimalScale AIScientist`
   - **Type**: Linux
   - **Version**: Ubuntu (64-bit)
   - **Memory**: 8192 MB
   - **Processors**: 4
   - **Hard disk**: Create a virtual hard disk now → **VDI** → **Dynamically allocated** → **64 GB**
3. Click **Finish**

### Configure Port Forwarding

1. Select the `OptimalScale AIScientist` VM → **Settings** → **Network**
2. Adapter 1 should be **NAT** (default)
3. Click **Advanced** → **Port Forwarding**
4. Add 3 rules (click the **+** icon):

| Name  | Protocol | Host IP   | Host Port | Guest IP | Guest Port |
|-------|----------|-----------|-----------|----------|------------|
| web   | TCP      | 127.0.0.1 | 5001      | 10.0.2.15 | 5001      |
| vnc   | TCP      | 127.0.0.1 | 6080      | 10.0.2.15 | 6080      |
| ssh   | TCP      | 127.0.0.1 | 2222      | 10.0.2.15 | 22        |

> Note: If host port 5001 is already in use on your PC, change it to 15001 or another free port.

5. Click **OK** → **OK**

### Attach the ISO

1. Select `OptimalScale AIScientist` VM → **Settings** → **Storage**
2. Click the **Empty** CD icon under Controller: IDE
3. Click the CD icon on the right → **Choose a disk file** → select the Ubuntu ISO
4. Click **OK**

---

## Step 2: Install Ubuntu

1. Click **Start** to boot the VM
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
     - Server name: `OptimalScale AIScientist`
     - Username: `aiscientist`
     - Password: `aiscientist`
   - SSH: **check** "Install OpenSSH server"
   - Featured Snaps: select nothing, click Done
3. Wait for installation (~5-10 minutes)
4. When you see "Reboot Now":
   - Go to **Devices** → **Optical Drives** → **Remove disk from virtual drive**
   - Then press Enter to reboot

### Enable SSH Password Authentication

After reboot, log in at the VirtualBox console (username: `aiscientist`, password: `aiscientist`):

```bash
sudo sed -i 's/^#*PasswordAuthentication.*/PasswordAuthentication yes/' /etc/ssh/sshd_config
sudo sed -i 's/^#*KbdInteractiveAuthentication.*/KbdInteractiveAuthentication yes/' /etc/ssh/sshd_config
sudo systemctl restart sshd
```

### Verify SSH from Windows

Open **PowerShell** or **Command Prompt**:

```bash
ssh -p 2222 aiscientist@localhost
# Password: aiscientist
```

---

## Step 3: Get Project Code

SSH into the VM and clone the repository:

```bash
ssh -p 2222 aiscientist@localhost
git clone -b feature-ai-scientists https://github.com/OptimalScale/controllable-sandbox.git ~/controllable-sandbox
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

This takes ~30-40 minutes. The script installs all dependencies (Docker, Conda, LaTeX, Python packages), builds the Docker sandbox image, configures auto-start services, and sets up the first-boot API key portal.

When complete, open `http://localhost:5001` (or your custom host port) in your Windows browser to verify the setup portal appears.

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

## Step 8: Export as .ova

1. In VirtualBox, make sure the VM is **powered off**
2. Go to **File** → **Export Appliance**
3. Select `OptimalScale AIScientist` → click **Next**
4. Format: **OVF 2.0**
5. File: choose a save location, e.g., `OptimalScale AIScientist-v1.0.0.ova`
6. Click **Next** → fill in description (optional) → click **Export**
7. Wait for export to complete (~10-20 minutes depending on disk size)

The resulting `.ova` file can be distributed to other VirtualBox users. They import it via **File** → **Import Appliance**.

---

## Troubleshooting

### SSH "Connection refused"

Make sure the VM is fully booted (wait 1-2 minutes) and port forwarding rule for port 22 → 2222 is configured.

### SSH "Permission denied"

Run the SSH password authentication fix from the VirtualBox console (Step 2).

### Website not loading

```bash
ssh -p 2222 aiscientist@localhost
sudo systemctl status sandbox-vm ai-scientists-web
```

If sandbox-vm failed, the Docker container likely crashed. Check:

```bash
docker ps -a
docker logs sandbox 2>&1 | tail -30
```

Common fix — workspace permission issue:

```bash
chmod 777 ~/controllable-sandbox/workspace
sudo systemctl restart sandbox-vm
sleep 30
sudo systemctl restart ai-scientists-web
```

### VirtualBox "VT-x is not available"

Enable virtualization in your PC's BIOS/UEFI settings (usually called "Intel VT-x" or "AMD-V"). This is required for VirtualBox to run 64-bit VMs.
