# OptimalScale AI Scientist — VM Quick Start

Use the pre-built virtual machine to run the AI Scientist Web UI with zero configuration.

---

## Requirements

| | Mac (Apple Silicon) | Windows / Linux Desktop | Linux Server (headless) |
|---|---|---|---|
| **VM Software** | [UTM](https://mac.getutm.app/) (free) | [VirtualBox 7.0+](https://www.virtualbox.org/) | [VirtualBox 7.0+](https://www.virtualbox.org/) |
| **VM File** | `.utm` | `.ova` | `.ova` |
| **RAM** | 8 GB min (16 GB recommended) | 8 GB min (16 GB recommended) | 8 GB min (16 GB recommended) |
| **Disk** | 30 GB free | 30 GB free | 30 GB free |
| **Web UI URL** | `http://localhost:15001` | `http://localhost:5001` | `http://localhost:5001` (via SSH tunnel) |

- **OpenAI API Key** (required) — Get one at https://platform.openai.com/
- **Firecrawl API Key** (optional, for citation search) — Get one at https://firecrawl.dev

---

## Getting Started

### 1. Import the VM

- **Mac**: Double-click the `.utm` file. UTM will open and add the VM automatically.
- **Windows / Linux Desktop**: Open VirtualBox → **File → Import Appliance** → select the `.ova` file → click **Import** (takes 5-10 minutes).
- **Linux Server**: Run on the server:
  ```bash
  VBoxManage import OptimalScale_AIScientist-v1.0.0.ova
  ```

### 2. Start the VM

- **Mac**: In UTM, select the VM and click the **play button**.
- **Windows / Linux Desktop**: In VirtualBox, select the VM and click **Start**.
- **Linux Server**:
  ```bash
  VBoxManage startvm "OptimalScale AIScientist" --type headless
  ```

Wait 1-2 minutes for the system to boot and services to initialize.

### 3. Access the Website

- **Mac**: Open `http://localhost:15001` in your browser.
- **Windows / Linux Desktop**: Open `http://localhost:5001` in your browser.
- **Linux Server**: The VM runs on a remote server, so you cannot access `localhost:5001` directly. Use **SSH port forwarding** to tunnel the ports to your local machine:

  Open a terminal **on your local computer** and run:
  ```bash
  ssh -L 5001:localhost:5001 -L 6080:localhost:6080 <username>@<server-ip>
  ```
  > Replace `<username>` and `<server-ip>` with your server login credentials.
  > Keep this terminal open — closing it will disconnect the tunnel.

  Then open `http://localhost:5001` in your **local browser**.

### 4. Configure API Keys

You will see the **OptimalScale AI Scientist Setup** page:

- Enter your **OpenAI API Key** (required)
- Optionally enter a **Firecrawl API Key** (for citation search)
- Click **Save & Start**

Wait ~60 seconds. The page will automatically redirect to the AI Scientist chat interface.

### 5. Generate a Proposal

- Describe your research topic in the chat
- Wait for the proposal to be generated
- Download the PDF and source files when complete

---

## Daily Usage

After the initial setup, you only need to:

1. Start the VM (UTM / VirtualBox / `VBoxManage startvm ... --type headless`)
2. Wait 1-2 minutes
3. **Linux Server only**: Open SSH tunnel (`ssh -L 5001:localhost:5001 <username>@<server-ip>`)
4. Open the website in your browser
5. Use the AI Scientist

The API keys are saved — you do not need to enter them again.

**Stop the VM when done** (Linux Server):
```bash
VBoxManage controlvm "OptimalScale AIScientist" acpipowerbutton
```

---

## SSH Access (Advanced)

```bash
ssh -p 2222 aiscientist@localhost
# Password: aiscientist
```

> On a Linux Server, run this command on the server itself, or tunnel port 2222 first:
> `ssh -L 2222:localhost:2222 <username>@<server-ip>`

### Reconfigure API Keys

```bash
ssh -p 2222 aiscientist@localhost
~/configure-keys.sh
```

### Check Service Status

```bash
ssh -p 2222 aiscientist@localhost
sudo systemctl status sandbox-vm ai-scientists-web
```

### View Logs

```bash
journalctl -u ai-scientists-web -f
```

### Restart Services

```bash
sudo systemctl restart sandbox-vm ai-scientists-web
```

---

## Optional: View Sandbox Browser

The AI Scientist pipeline uses a sandboxed browser for citation search. You can watch it in action:

- **Mac**: `http://localhost:6080/vnc_auto.html`
- **Windows / Linux Desktop**: `http://localhost:6080/vnc_auto.html`
- **Linux Server**: `http://localhost:6080/vnc_auto.html` (after SSH tunnel with `-L 6080:localhost:6080`)

Password: `agent2k`

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Website not loading | Wait 1-2 minutes after starting the VM. Services need time to initialize. |
| Setup page not appearing | SSH in and run: `rm ~/.setup-complete && sudo systemctl restart ai-scientists-setup` |
| "Agent exited without completing" | SSH in and run: `sudo systemctl restart sandbox-vm && sleep 30 && sudo systemctl restart ai-scientists-web` |
| Need to change API keys | SSH in and run: `~/configure-keys.sh` |
| VM feels slow | Shut down VM, increase RAM/CPU in VM settings |

### SSH "Permission denied (publickey)"

This means password-based SSH login is disabled. Fix it from the VM console (UTM/VirtualBox window):

1. Log in at the console: username `aiscientist`, password `aiscientist`
2. Run:
   ```bash
   sudo sed -i 's/^#*PasswordAuthentication.*/PasswordAuthentication yes/' /etc/ssh/sshd_config
   sudo sed -i 's/^#*KbdInteractiveAuthentication.*/KbdInteractiveAuthentication yes/' /etc/ssh/sshd_config
   sudo systemctl restart sshd
   ```

> On a headless Linux server without a VM console, you may need to stop the VM, mount its disk, and fix sshd_config manually.

### Port conflict on VM start

If the VM fails to start because a port is already in use:

- **UTM (Mac)**: Right-click VM → Edit → Network → Port Forward → change the host port
- **VirtualBox**: Settings → Network → Port Forwarding → change the host port
- **Linux Server**: Use a different local port in the SSH tunnel, e.g. `-L 15001:localhost:5001`, then access `http://localhost:15001`

---

## Port Reference

| | Mac (UTM) | Windows / Linux Desktop | Linux Server (tunnel) |
|---|---|---|---|
| Web UI | 15001 | 5001 | `-L 5001:localhost:5001` |
| noVNC | 6080 | 6080 | `-L 6080:localhost:6080` |
| SSH | 2222 | 2222 | `-L 2222:localhost:2222` |
