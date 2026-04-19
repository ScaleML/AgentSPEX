# AI Scientists VM — Quick Start Guide

One-click deployment of the AI Scientists research proposal generator.

---

## System Requirements

- **VirtualBox 7.0+** — Download from https://www.virtualbox.org/
- **RAM**: 8 GB minimum (16 GB recommended on host machine)
- **Disk**: 30 GB free space
- **Internet**: Required for OpenAI API calls
- **API Key**: An OpenAI API key (`sk-...`) from https://platform.openai.com/

---

## Step 1: Import the VM

1. Download `ai-scientists-v1.0.0.ova`
2. Open VirtualBox
3. **File > Import Appliance** > select the `.ova` file
4. Review settings (adjust RAM/CPU if desired)
5. Click **Import** (takes 5-10 minutes)

---

## Step 2: Configure API Keys

1. Start the VM from VirtualBox Manager (click **Start**)
2. Wait 30-60 seconds for services to boot
3. Open **http://localhost:5001** in your host browser
4. You will see the **Setup Portal**:
   - Enter your **OpenAI API Key** (required)
   - Optionally enter a **Firecrawl API Key** (for citation search, get one at https://firecrawl.dev)
5. Click **Save & Start**
6. Wait ~30 seconds for services to initialize

---

## Step 3: Use the Web UI

1. After setup, **http://localhost:5001** shows the AI Scientists chat interface
2. Accept the disclaimer
3. Describe your research domain and intent
4. Wait for proposal generation:
   - **Fast mode**: ~5 minutes (short proposal)
   - **Full mode**: ~25 minutes (comprehensive proposal with citations)
5. Download the **PDF** and **source files** when complete

---

## Optional: View the Sandbox Desktop

The AI Scientists pipeline uses a sandboxed browser for citation search. You can watch it in action:

- Open **http://localhost:6080/vnc_auto.html** in your browser
- Password: `agent2k`

---

## SSH Access (Advanced)

```bash
ssh -p 2222 aiscientist@localhost
# Password: aiscientist
```

### Reconfigure API Keys via CLI

```bash
ssh -p 2222 aiscientist@localhost
~/configure-keys.sh
```

### Service Management

```bash
# Check service status
sudo systemctl status sandbox-vm ai-scientists-web

# View web UI logs
journalctl -u ai-scientists-web -f

# Restart all services
sudo systemctl restart sandbox-vm ai-scientists-web

# View sandbox container logs
docker logs sandbox -f
```

---

## Troubleshooting

### Port 5001 not reachable

Wait 60 seconds after starting the VM — services need time to initialize. If still not working:

```bash
ssh -p 2222 aiscientist@localhost
sudo systemctl status ai-scientists-web
sudo systemctl status ai-scientists-setup
```

### "Connection refused on MCP port"

The sandbox Docker container may still be starting:

```bash
ssh -p 2222 aiscientist@localhost
sudo systemctl restart sandbox-vm
# Wait 30 seconds, then:
sudo systemctl restart ai-scientists-web
```

### PDF compilation fails

LaTeX is pre-installed in the VM. If you see missing package errors in the logs:

```bash
ssh -p 2222 aiscientist@localhost
sudo apt install texlive-<package-name>
```

### Change API keys after initial setup

```bash
ssh -p 2222 aiscientist@localhost
~/configure-keys.sh
```

Or edit the file directly:

```bash
nano ~/controllable-sandbox/config/vm.env
sudo systemctl restart sandbox-vm ai-scientists-web
```

---

## Resource Adjustment

To change RAM or CPU allocation:

1. Shut down the VM
2. In VirtualBox: select the VM > **Settings** > **System**
3. Adjust **Base Memory** and **Processor(s)**
4. Click **OK** and restart

---

## Port Reference

| Host Port | Purpose |
|-----------|---------|
| 5001 | Web UI (or Setup Portal on first boot) |
| 6080 | noVNC sandbox browser viewer |
| 2222 | SSH access |
