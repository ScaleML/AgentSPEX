# Building the AI Scientist VM on Ubuntu (Host)

This guide covers how to create a distributable `.ova` virtual machine image for the OptimalScale AI Scientist Web UI on an **Ubuntu host** (desktop or headless server) using VirtualBox.

> **Lessons learned**: We tested multiple approaches on an Ubuntu cloud server.
> The **Ubuntu Cloud Image** method (Option B below) is the most reliable for headless servers.
> See the [Approaches That Did NOT Work](#approaches-that-did-not-work) section at the end for details.

---

## Prerequisites

- **Ubuntu 20.04/22.04/24.04** (64-bit, as the host OS)
- **VirtualBox 7.0+** (6.1 has critical limitations on headless servers — see [Known Issues](#known-issues))
- **16 GB RAM** recommended (8 GB minimum)
- **70 GB** free disk space (cloud image ~700MB + VDI ~2-8GB + exported .ova ~7-8GB)
- **sshpass** (for scripted SSH into the VM)
- **qemu-utils** (for Option B: cloud image conversion)

### Install VirtualBox 7.0+

The default Ubuntu repo may only have VirtualBox 6.1. **You must use 7.0+** for headless builds.

```bash
# Add Oracle VirtualBox repo
wget -qO- https://www.virtualbox.org/download/oracle_vbox_2016.asc \
  | sudo gpg --dearmor -o /usr/share/keyrings/oracle-virtualbox.gpg

echo "deb [signed-by=/usr/share/keyrings/oracle-virtualbox.gpg] \
  https://download.virtualbox.org/virtualbox/debian $(lsb_release -cs) contrib" \
  | sudo tee /etc/apt/sources.list.d/virtualbox.list

sudo apt update && sudo apt install -y virtualbox-7.0
```

> **Important**: If VirtualBox 6.1 is already installed, remove it first (`sudo apt remove virtualbox`) and kill all VBox processes (`pkill -f VBox`) before installing 7.0. The 7.0 installer will refuse to proceed if any VBox process is running.

### Install other tools

```bash
sudo apt install -y sshpass qemu-utils genisoimage
```

### Verify nested virtualization (if host is a VM)

If your Ubuntu host is itself a VM (e.g., cloud instance), check nested virtualization:

```bash
grep -E 'vmx|svm' /proc/cpuinfo
```

If empty, nested virtualization is not available and you cannot create VMs inside this host.

---

## Option A: GUI Desktop (with monitor)

If your Ubuntu host has a GUI, this is the simplest approach — manually install Ubuntu in a VirtualBox window.

### Step 1: Download Ubuntu Server ISO

```bash
wget https://releases.ubuntu.com/22.04.5/ubuntu-22.04.5-live-server-amd64.iso
```

### Step 2: Create the VM in VirtualBox GUI

1. Open VirtualBox → click **New**
2. Configure:
   - **Name**: `OptimalScale AIScientist`
   - **Type**: Linux
   - **Version**: Ubuntu (64-bit)
   - **Memory**: 8192 MB
   - **Processors**: 4
   - **Hard disk**: Create a virtual hard disk now → **VDI** → **Dynamically allocated** → **64 GB**
3. Click **Finish**

### Step 3: Configure Port Forwarding

1. Select the `OptimalScale AIScientist` VM → **Settings** → **Network**
2. Adapter 1 should be **NAT** (default)
3. Click **Advanced** → **Port Forwarding**
4. Add 3 rules (click the **+** icon):

| Name  | Protocol | Host IP   | Host Port | Guest IP  | Guest Port |
|-------|----------|-----------|-----------|-----------|------------|
| web   | TCP      | 127.0.0.1 | 5001      | 10.0.2.15 | 5001       |
| vnc   | TCP      | 127.0.0.1 | 6080      | 10.0.2.15 | 6080       |
| ssh   | TCP      | 127.0.0.1 | 2222      | 10.0.2.15 | 22         |

> Note: If host port 5001 is already in use, change it to 15001 or another free port.

5. Click **OK** → **OK**

### Step 4: Attach the ISO and install Ubuntu

1. Select `OptimalScale AIScientist` VM → **Settings** → **Storage**
2. Click the **Empty** CD icon under Controller: IDE
3. Click the CD icon on the right → **Choose a disk file** → select the Ubuntu ISO
4. Click **OK**, then click **Start** to boot the VM
5. Follow the Ubuntu installer:
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
6. Wait for installation (~5-10 minutes)
7. When you see "Reboot Now":
   - Go to **Devices** → **Optical Drives** → **Remove disk from virtual drive**
   - Then press Enter to reboot

### Step 5: Enable SSH Password Authentication

After reboot, log in at the VirtualBox console (username: `aiscientist`, password: `aiscientist`):

```bash
sudo sed -i 's/^#*PasswordAuthentication.*/PasswordAuthentication yes/' /etc/ssh/sshd_config
sudo sed -i 's/^#*KbdInteractiveAuthentication.*/KbdInteractiveAuthentication yes/' /etc/ssh/sshd_config
sudo systemctl restart sshd
```

Then continue to [Get Project Code](#get-project-code).

---

## Option B: Headless Server (no monitor) — Recommended

This approach uses a **pre-built Ubuntu Cloud Image** instead of installing from ISO. It is the most reliable method for headless servers (cloud instances, remote servers, CI/CD).

### Step 1: Download the Ubuntu 22.04 Cloud Image

```bash
wget -O ~/ubuntu-22.04-server-cloudimg-amd64.img \
  https://cloud-images.ubuntu.com/releases/22.04/release/ubuntu-22.04-server-cloudimg-amd64.img
```

### Step 2: Convert to VDI and resize

```bash
# Convert qcow2 cloud image to VirtualBox VDI format
qemu-img convert -f qcow2 -O vdi \
  ~/ubuntu-22.04-server-cloudimg-amd64.img \
  ~/disk.vdi

# Resize the disk to 64GB
VBoxManage modifymedium disk ~/disk.vdi --resize 65536
```

### Step 3: Create a cloud-init seed ISO

The cloud image uses cloud-init for initial configuration. Create a seed ISO with user credentials:

```bash
mkdir -p /tmp/cidata

cat > /tmp/cidata/user-data << 'EOF'
#cloud-config
hostname: ai-scientists
users:
  - name: aiscientist
    plain_text_passwd: aiscientist
    lock_passwd: false
    sudo: ALL=(ALL) NOPASSWD:ALL
    shell: /bin/bash
    groups: [sudo, docker]
ssh_pwauth: true
chpasswd:
  expire: false
package_update: false
runcmd:
  - sed -i 's/^#*PasswordAuthentication.*/PasswordAuthentication yes/' /etc/ssh/sshd_config
  - sed -i 's/^#*KbdInteractiveAuthentication.*/KbdInteractiveAuthentication yes/' /etc/ssh/sshd_config
  - systemctl restart sshd
  - growpart /dev/sda 1 || true
  - resize2fs /dev/sda1 || true
EOF

cat > /tmp/cidata/meta-data << 'EOF'
instance-id: ai-scientists-001
local-hostname: ai-scientists
EOF

genisoimage -output ~/seed.iso -volid cidata -joliet -rock /tmp/cidata/
```

> **Key detail**: The volume label must be `cidata` — this is how cloud-init detects the NoCloud datasource.

### Step 4: Create and configure the VM

```bash
VM_NAME="OptimalScale AIScientist"

# Create VM
VBoxManage createvm --name "$VM_NAME" --ostype Ubuntu_64 --register
VBoxManage modifyvm "$VM_NAME" --cpus 4 --memory 8192 --vram 16

# Move VDI to VM directory
cp ~/disk.vdi ~/VirtualBox\ VMs/OptimalScale\ AIScientist/disk.vdi

# Attach disk (SATA controller)
VBoxManage storagectl "$VM_NAME" --name "SATA" --add sata --controller IntelAhci
VBoxManage storageattach "$VM_NAME" --storagectl "SATA" --port 0 --device 0 \
  --type hdd --medium ~/VirtualBox\ VMs/OptimalScale\ AIScientist/disk.vdi

# Attach cloud-init seed ISO (IDE controller)
VBoxManage storagectl "$VM_NAME" --name "IDE" --add ide
VBoxManage storageattach "$VM_NAME" --storagectl "IDE" --port 0 --device 0 \
  --type dvddrive --medium ~/seed.iso

# Network: NAT with port forwarding
VBoxManage modifyvm "$VM_NAME" --nic1 nat --nat-localhostreachable1 on
VBoxManage modifyvm "$VM_NAME" --natpf1 "web,tcp,,5001,,5001"
VBoxManage modifyvm "$VM_NAME" --natpf1 "vnc,tcp,,6080,,6080"
VBoxManage modifyvm "$VM_NAME" --natpf1 "ssh,tcp,,2222,,22"
```

### Step 5: Start VM and verify SSH

```bash
VBoxManage startvm "$VM_NAME" --type headless

# Wait ~90 seconds for cloud-init to finish, then test SSH
sleep 90
sshpass -p "aiscientist" ssh -o StrictHostKeyChecking=no -p 2222 aiscientist@localhost \
  "echo SSH_OK && hostname && df -h /"
```

Expected output:
```
SSH_OK
ai-scientists
Filesystem      Size  Used Avail Use% Mounted on
/dev/sda1        62G  1.6G   61G   3% /
```

> **Tip**: If SSH fails, wait another minute and retry. Cloud-init may still be running.

Then continue to [Get Project Code](#get-project-code).

---

## Get Project Code

SSH into the VM and clone the repository:

```bash
sshpass -p "aiscientist" ssh -o StrictHostKeyChecking=no -p 2222 aiscientist@localhost
git clone -b feature-ai-scientists https://github.com/OptimalScale/controllable-sandbox.git ~/controllable-sandbox
```

**Alternative** — transfer from local machine (useful if you have local changes):

```bash
# On your Ubuntu host
cd /path/to/project
tar czf /tmp/controllable-sandbox.tar.gz \
    --exclude='controllable-sandbox/workspace' \
    --exclude='controllable-sandbox/workspace_persistent' \
    --exclude='controllable-sandbox/outputs' \
    --exclude='controllable-sandbox/.git' \
    controllable-sandbox/

scp -P 2222 /tmp/controllable-sandbox.tar.gz aiscientist@localhost:~/

# Inside the VM
sshpass -p "aiscientist" ssh -p 2222 aiscientist@localhost \
  "tar xzf ~/controllable-sandbox.tar.gz -C ~/ && rm ~/controllable-sandbox.tar.gz"
```

---

## Accept Conda ToS (IMPORTANT)

After `install.sh` installs Conda, it may fail with a `CondaToSNonInteractiveError`. You **must** accept the Terms of Service before Conda can create environments:

```bash
sshpass -p "aiscientist" ssh -p 2222 aiscientist@localhost bash -c '
  ~/miniconda3/bin/conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/main
  ~/miniconda3/bin/conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/r
'
```

> **Note**: This step is needed because recent versions of Conda (2025+) require explicit ToS acceptance. If `install.sh` fails at the Conda step, accept the ToS and re-run the script — it is idempotent and will skip already-completed steps.

---

## Run install.sh

```bash
sshpass -p "aiscientist" ssh -o ServerAliveInterval=60 -p 2222 aiscientist@localhost \
  "cd ~/controllable-sandbox && sudo bash demo/ai_scientists/install.sh"
```

This takes **~30-40 minutes**. The script will:
1. Install system packages (build-essential, git, curl, etc.)
2. Install Docker and add `aiscientist` to the docker group
3. Install Conda + create `yaml_agent` environment with Python 3.12 and all dependencies
4. Install LaTeX toolchain (texlive)
5. Configure project directories and environment files
6. Build the Docker sandbox image (~10-20 minutes)
7. Configure systemd services for auto-start on boot
8. Install the first-boot API key setup portal
9. Set permissions and start the setup service

> **If it fails at the Conda step**: Accept the ToS (see above) and re-run. The script is idempotent.

When complete, verify: `http://localhost:5001` should show the setup portal.

---

## Test the Website

1. Open `http://localhost:5001` in your host browser
2. Enter your OpenAI API Key on the setup page
3. Click **Save & Start**
4. Wait ~60 seconds for services to start
5. Refresh the page — you should see the AI Scientist chat interface
6. Try generating a proposal to verify everything works

---

## Clean Private Data Before Distribution

SSH into the VM and run:

```bash
sshpass -p "aiscientist" ssh -p 2222 aiscientist@localhost bash << 'EOF'
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

# Clean cloud-init state (prevents re-running on import)
sudo cloud-init clean --logs 2>/dev/null || true
sudo rm -rf /var/lib/cloud/instances/*

# Delete misc files
rm -f ~/.sudo_as_admin_successful
rm -rf ~/.cache

# Clear shell history
history -c
> ~/.bash_history

# Shut down
sudo shutdown now
EOF
```

---

## Export as .ova

After the VM shuts down:

```bash
# Remove the cloud-init seed ISO (not needed by end users)
VBoxManage storageattach "OptimalScale AIScientist" \
  --storagectl "IDE" --port 0 --device 0 --type dvddrive --medium emptydrive

# Export as .ova
VBoxManage export "OptimalScale AIScientist" \
  -o ~/OptimalScale_AIScientist-v1.0.0.ova --ovf20
```

The resulting `.ova` file (~7-8 GB) can be distributed to any VirtualBox user (Linux/Windows/Mac). They import it via **File** → **Import Appliance** or:

```bash
VBoxManage import OptimalScale_AIScientist-v1.0.0.ova
```

---

## Known Issues

### VirtualBox 6.1 does NOT work for headless builds

Ubuntu's default repo installs VirtualBox 6.1 which has two critical issues for headless VM builds:

1. **`--nat-localhostreachable1` option not supported** (added in 7.0)
2. **`Failed to send a scancode`** error — VBox 6.1 cannot send keyboard input to headless VMs, making automated ISO installs impossible

**Fix**: Install VirtualBox 7.0+ from the Oracle repo (see Prerequisites).

### VBox 7.0 installation fails: "Running VMs found"

If VirtualBox 6.1 was previously running, residual VBox processes block the 7.0 installer.

**Fix**:
```bash
sudo apt remove -y virtualbox
pkill -f VBox
sleep 5
sudo apt install -y virtualbox-7.0
```

### Packer `boot_command` SSH timeout

Packer's `virtualbox-iso` builder sends GRUB keystrokes to automate Ubuntu installation. In nested virtualization environments, this is unreliable — the VM may not process keystrokes correctly, causing the installer to hang at the GRUB menu or skip autoinstall.

**Fix**: Use the Cloud Image approach (Option B) instead of Packer/ISO.

### VBoxManage `unattended install` incompatible with Ubuntu 22.04 Server

`VBoxManage unattended install` uses Debian preseed, but Ubuntu 22.04 **Server** uses subiquity/autoinstall. The two systems are incompatible.

**Fix**: Use the Cloud Image approach (Option B) or GUI install (Option A).

### Conda `CondaToSNonInteractiveError`

Recent Conda versions (2025+) require explicit Terms of Service acceptance. `install.sh` will fail at the Conda environment creation step.

**Fix**: Accept ToS before running install.sh:
```bash
~/miniconda3/bin/conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/main
~/miniconda3/bin/conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/r
```
Then re-run `install.sh` — it is idempotent.

### SSH "REMOTE HOST IDENTIFICATION HAS CHANGED"

If you rebuild the VM, the SSH host key changes. `sshpass` and `ssh` will refuse to connect.

**Fix**:
```bash
ssh-keygen -f ~/.ssh/known_hosts -R "[localhost]:2222"
```

---

## Approaches That Did NOT Work

For reference, here are the approaches we tested on a headless Ubuntu cloud server (nested VM) and why they failed:

| Approach | Problem |
|---|---|
| **Packer + ISO** (`boot_command`) | VBox 6.1: can't send scancodes in headless mode. VBox 7.0: boot_command unreliable in nested virt — SSH timeout after 45 min |
| **VBoxManage `unattended install`** | Uses Debian preseed, incompatible with Ubuntu 22.04 Server (which uses subiquity/autoinstall) |
| **ISO + seed ISO** (no `autoinstall` kernel param) | Installer detects cloud-init config but waits for interactive confirmation — no way to confirm without a display |
| **ISO + GRUB boot command** (via `keyboardputstring`) | Boot commands sent successfully but autoinstall still didn't complete — likely a timing/GRUB issue in nested virt |

**What works**: Ubuntu Cloud Image (pre-installed qcow2) + cloud-init seed ISO. No OS installation needed — boots directly into a configured system in ~90 seconds.

---

## Troubleshooting

### SSH "Connection refused"

Make sure the VM is fully booted (wait 1-2 minutes) and port forwarding rule for port 22 → 2222 is configured.

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

### VirtualBox "VT-x/AMD-V is not available"

Enable virtualization in your PC's BIOS/UEFI settings (usually called "Intel VT-x" or "AMD-V").

### VirtualBox kernel module not loaded

```bash
sudo modprobe vboxdrv
# If this fails, reinstall kernel headers:
sudo apt install -y linux-headers-$(uname -r)
sudo /sbin/vboxconfig
```
