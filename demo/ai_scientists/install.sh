#!/bin/bash
###############################################################################
# install.sh — OptimalScale AI Scientist Web UI One-Click Installer
#
# Run this script on a clean Ubuntu 22.04 machine to set up everything.
# After installation, open http://localhost:5001 and enter your API Key.
#
# Usage:
#   cd controllable-sandbox
#   sudo bash demo/ai_scientists/install.sh
#
###############################################################################
set -euo pipefail

# ── Output helpers ──────────────────────────────────────────────────────────
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

step() { echo -e "\n${GREEN}[✓ STEP $1/$TOTAL_STEPS]${NC} $2"; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }
fail() { echo -e "${RED}[✗]${NC} $1"; exit 1; }

TOTAL_STEPS=9

# ── Prerequisites ───────────────────────────────────────────────────────────
if [ "$EUID" -ne 0 ]; then
    fail "Please run with sudo: sudo ./install.sh"
fi

# install.sh lives at demo/ai_scientists/ — go up 2 levels to reach project root
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
if [ ! -f "$PROJECT_DIR/config/Dockerfile" ]; then
    fail "Please run this script from the controllable-sandbox directory"
fi

# Detect the actual user (before sudo)
REAL_USER="${SUDO_USER:-$(whoami)}"
REAL_HOME=$(eval echo "~$REAL_USER")

echo "============================================"
echo " OptimalScale AI Scientist — Installer"
echo "============================================"
echo " Project dir:  $PROJECT_DIR"
echo " User:         $REAL_USER"
echo " Architecture: $(uname -m)"
echo "============================================"

export DEBIAN_FRONTEND=noninteractive

###############################################################################
# Step 1: Base system packages
###############################################################################
step 1 "Installing base system packages..."
apt-get update -qq
apt-get install -y -qq \
    build-essential gcc g++ make \
    git curl wget \
    ca-certificates gnupg lsb-release \
    software-properties-common \
    openssh-server \
    htop tmux jq unzip zip \
    net-tools iproute2 \
    > /dev/null

###############################################################################
# Step 2: Docker
###############################################################################
step 2 "Installing Docker..."
if command -v docker &>/dev/null; then
    warn "Docker already installed, skipping"
else
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
        | gpg --dearmor -o /etc/apt/keyrings/docker.gpg 2>/dev/null
    chmod a+r /etc/apt/keyrings/docker.gpg

    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
        https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" \
        > /etc/apt/sources.list.d/docker.list

    apt-get update -qq
    apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin > /dev/null
fi

usermod -aG docker "$REAL_USER" 2>/dev/null || true
systemctl enable docker --now

###############################################################################
# Step 3: Conda + Python environment
###############################################################################
step 3 "Installing Conda + Python environment (this may take ~10 minutes)..."
CONDA_DIR="$REAL_HOME/miniconda3"
CONDA_ENV="yaml_agent"

if [ ! -d "$CONDA_DIR" ]; then
    ARCH=$(uname -m)
    wget -q "https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-${ARCH}.sh" -O /tmp/miniconda.sh
    bash /tmp/miniconda.sh -b -p "$CONDA_DIR"
    rm /tmp/miniconda.sh
    chown -R "$REAL_USER:$REAL_USER" "$CONDA_DIR"
    sudo -u "$REAL_USER" "$CONDA_DIR/bin/conda" init bash
else
    warn "Conda already installed, skipping"
fi

if [ ! -d "$CONDA_DIR/envs/$CONDA_ENV" ]; then
    sudo -u "$REAL_USER" "$CONDA_DIR/bin/conda" create -y -n "$CONDA_ENV" python=3.12
else
    warn "yaml_agent environment already exists, skipping"
fi

PIP="$CONDA_DIR/envs/$CONDA_ENV/bin/pip"

# PyTorch (CPU only — all LLM inference goes through OpenAI API)
if ! sudo -u "$REAL_USER" "$CONDA_DIR/envs/$CONDA_ENV/bin/python" -c "import torch" 2>/dev/null; then
    ARCH=$(uname -m)
    if [ "$ARCH" = "aarch64" ]; then
        sudo -u "$REAL_USER" $PIP install -q torch==2.8.0
    else
        sudo -u "$REAL_USER" $PIP install -q torch==2.8.0 --index-url https://download.pytorch.org/whl/cpu
    fi
else
    warn "PyTorch already installed, skipping"
fi

# Project dependencies
sudo -u "$REAL_USER" $PIP install -q -r "$PROJECT_DIR/requirements.txt"
sudo -u "$REAL_USER" $PIP install -q -e "$PROJECT_DIR/"
sudo -u "$REAL_USER" $PIP install -q flask litellm

###############################################################################
# Step 4: LaTeX
###############################################################################
step 4 "Installing LaTeX toolchain..."
if command -v pdflatex &>/dev/null; then
    warn "LaTeX already installed, skipping"
else
    apt-get install -y -qq \
        texlive-latex-base texlive-latex-recommended \
        texlive-fonts-recommended texlive-science texlive-latex-extra \
        > /dev/null
fi

###############################################################################
# Step 5: Project configuration
###############################################################################
step 5 "Configuring project files..."
mkdir -p "$PROJECT_DIR/workspace" "$PROJECT_DIR/workspace_persistent" "$PROJECT_DIR/outputs"
chown -R "$REAL_USER:$REAL_USER" "$PROJECT_DIR/workspace" "$PROJECT_DIR/workspace_persistent" "$PROJECT_DIR/outputs"
# Docker container's agent user needs write access to workspace
chmod 777 "$PROJECT_DIR/workspace"

# Deploy PRIMEarxiv.sty to workspace root so pdflatex can find it from Docker
cp "$PROJECT_DIR/demo/ai_scientists/PRIMEarxiv.sty" "$PROJECT_DIR/workspace/PRIMEarxiv.sty"
chown "$REAL_USER:$REAL_USER" "$PROJECT_DIR/workspace/PRIMEarxiv.sty"

# Ensure API key lines exist in vm.env (do not overwrite existing values)
if ! grep -q "^OPENAI_API_KEY=" "$PROJECT_DIR/config/vm.env" 2>/dev/null; then
    echo "OPENAI_API_KEY=" >> "$PROJECT_DIR/config/vm.env"
fi

# Create host.env if it does not exist
if [ ! -f "$PROJECT_DIR/config/host.env" ]; then
    cat > "$PROJECT_DIR/config/host.env" << 'EOF'
HOST_WORKSPACE=$(pwd)/workspace
WORKSPACE_PERSISTENT=$(pwd)/workspace_persistent
EOF
fi

###############################################################################
# Step 6: Docker sandbox image
###############################################################################
step 6 "Building Docker sandbox image (this may take ~10-20 minutes)..."
if docker images virtual-sandbox:latest --format "{{.ID}}" | grep -q .; then
    warn "Docker image already exists, skipping build"
else
    cd "$PROJECT_DIR"
    docker build -t virtual-sandbox:latest -f config/Dockerfile .
fi

###############################################################################
# Step 7: systemd services
###############################################################################
step 7 "Configuring auto-start services..."

# sandbox-vm.service
cat > /etc/systemd/system/sandbox-vm.service << EOF
[Unit]
Description=AI Scientists Sandbox VM (Docker container)
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
User=$REAL_USER
WorkingDirectory=$PROJECT_DIR
ExecStart=/bin/bash scripts/run_vm.sh start
ExecStop=/bin/bash scripts/run_vm.sh stop
TimeoutStartSec=120

[Install]
WantedBy=multi-user.target
EOF

# ai-scientists-web.service
cat > /etc/systemd/system/ai-scientists-web.service << EOF
[Unit]
Description=AI Scientists Flask Web UI
After=sandbox-vm.service
Requires=sandbox-vm.service

[Service]
Type=simple
User=$REAL_USER
WorkingDirectory=$PROJECT_DIR
Environment="PATH=$CONDA_DIR/envs/$CONDA_ENV/bin:$CONDA_DIR/bin:/usr/local/bin:/usr/bin:/bin"
Environment="CONDA_DEFAULT_ENV=$CONDA_ENV"
Environment="HOME=$REAL_HOME"
ExecStartPre=/bin/bash -c 'for i in \$(seq 1 30); do curl -sf http://localhost:7002/mcp > /dev/null 2>&1 && exit 0 || sleep 2; done; echo "WARNING: MCP not ready after 60s, starting anyway"'
ExecStart=$CONDA_DIR/envs/$CONDA_ENV/bin/python demo/ai_scientists/web/app.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# ai-scientists-setup.service (first-boot setup portal)
cat > /etc/systemd/system/ai-scientists-setup.service << EOF
[Unit]
Description=AI Scientists First-Boot Setup Portal
After=network-online.target
Wants=network-online.target
ConditionPathExists=!$REAL_HOME/.setup-complete

[Service]
Type=simple
User=$REAL_USER
Environment="PATH=$CONDA_DIR/envs/$CONDA_ENV/bin:$CONDA_DIR/bin:/usr/local/bin:/usr/bin:/bin"
Environment="HOME=$REAL_HOME"
ExecStart=$CONDA_DIR/envs/$CONDA_ENV/bin/python $REAL_HOME/setup-portal/setup_server.py
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable sandbox-vm.service ai-scientists-web.service ai-scientists-setup.service

###############################################################################
# Step 8: Setup portal + CLI tool
###############################################################################
step 8 "Installing API key configuration tools..."

SETUP_DIR="$REAL_HOME/setup-portal"
mkdir -p "$SETUP_DIR/templates"

# setup_server.py
cat > "$SETUP_DIR/setup_server.py" << 'PYEOF'
import os, re, subprocess, sys
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)
VM_ENV_PATH = os.path.expanduser("~/controllable-sandbox/config/vm.env")
SETUP_SENTINEL = os.path.expanduser("~/.setup-complete")

def _update_env_key(filepath, key, value):
    with open(filepath, "r") as f:
        content = f.read()
    content = re.sub(rf"^{re.escape(key)}=.*$", f"{key}={value}", content, flags=re.MULTILINE)
    with open(filepath, "w") as f:
        f.write(content)

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/setup", methods=["POST"])
def setup():
    data = request.get_json()
    openai_key = (data.get("openai_api_key") or "").strip()
    firecrawl_key = (data.get("firecrawl_api_key") or "").strip()
    if not openai_key:
        return jsonify({"error": "OPENAI_API_KEY is required"}), 400
    try:
        _update_env_key(VM_ENV_PATH, "OPENAI_API_KEY", openai_key)
        if firecrawl_key:
            _update_env_key(VM_ENV_PATH, "FIRECRAWL_API_KEY", firecrawl_key)
        open(SETUP_SENTINEL, "w").close()
        subprocess.Popen(["bash", "-c",
            "sudo systemctl start sandbox-vm.service && "
            "sudo systemctl start ai-scientists-web.service && "
            "sleep 2 && sudo systemctl stop ai-scientists-setup.service"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return jsonify({"status": "ok",
            "message": "API keys saved. Starting services... Page will redirect in ~60 seconds."})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    if os.path.exists(SETUP_SENTINEL):
        print("Setup already completed."); sys.exit(0)
    print("Setup Portal: http://0.0.0.0:5001")
    app.run(host="0.0.0.0", port=5001, debug=False)
PYEOF

# setup HTML template
cat > "$SETUP_DIR/templates/index.html" << 'HTMLEOF'
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>OptimalScale AI Scientist — Setup</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#0f172a;color:#e2e8f0;min-height:100vh;display:flex;align-items:center;justify-content:center}
.c{background:#1e293b;border-radius:16px;padding:48px;max-width:520px;width:90%;box-shadow:0 25px 50px rgba(0,0,0,.4)}
h1{font-size:24px;margin-bottom:8px;color:#f8fafc}
.sub{color:#94a3b8;margin-bottom:32px;font-size:14px;line-height:1.5}
.fg{margin-bottom:24px}
label{display:block;font-size:14px;font-weight:600;margin-bottom:8px;color:#cbd5e1}
.req{color:#f87171}.opt{color:#64748b;font-weight:400;font-size:12px;margin-left:4px}
input{width:100%;padding:12px 16px;background:#0f172a;border:1px solid #334155;border-radius:8px;color:#e2e8f0;font-size:14px;font-family:'SF Mono',Monaco,monospace}
input:focus{outline:none;border-color:#3b82f6}
.hint{font-size:12px;color:#64748b;margin-top:6px}
.btn{width:100%;padding:14px;background:#3b82f6;color:#fff;border:none;border-radius:8px;font-size:16px;font-weight:600;cursor:pointer;margin-top:8px}
.btn:hover{background:#2563eb}.btn:disabled{background:#475569;cursor:not-allowed}
.msg{margin-top:16px;padding:12px 16px;border-radius:8px;font-size:14px;display:none}
.msg.ok{background:#064e3b;border:1px solid #059669;color:#6ee7b7;display:block}
.msg.err{background:#450a0a;border:1px solid #dc2626;color:#fca5a5;display:block}
.sp{display:inline-block;width:16px;height:16px;border:2px solid #ffffff40;border-top-color:#fff;border-radius:50%;animation:s .8s linear infinite;margin-right:8px;vertical-align:middle}
@keyframes s{to{transform:rotate(360deg)}}
</style>
</head>
<body>
<div class="c">
<h1>OptimalScale AI Scientist Setup</h1>
<p class="sub">Welcome! Configure your API keys to get started. This page only appears on first boot.</p>
<div class="fg">
<label>OpenAI API Key <span class="req">*</span></label>
<input type="password" id="k1" placeholder="sk-..." autocomplete="off">
<p class="hint">Required. Get one at platform.openai.com</p>
</div>
<div class="fg">
<label>Firecrawl API Key <span class="opt">(optional)</span></label>
<input type="password" id="k2" placeholder="fc-..." autocomplete="off">
<p class="hint">For citation search. Get one at firecrawl.dev</p>
</div>
<button class="btn" id="btn" onclick="go()">Save & Start</button>
<div class="msg" id="msg"></div>
</div>
<script>
async function go(){
const b=document.getElementById('btn'),m=document.getElementById('msg'),v1=document.getElementById('k1').value.trim(),v2=document.getElementById('k2').value.trim();
if(!v1){m.className='msg err';m.textContent='OpenAI API Key is required.';return}
b.disabled=true;b.innerHTML='<span class="sp"></span>Saving...';m.style.display='none';
try{const r=await fetch('/api/setup',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({openai_api_key:v1,firecrawl_api_key:v2})});const d=await r.json();
if(r.ok){m.className='msg ok';m.textContent=d.message;b.innerHTML='<span class="sp"></span>Starting services...';setTimeout(()=>{m.textContent+=' Redirecting...';setTimeout(()=>window.location.reload(),15000)},45000)}
else{m.className='msg err';m.textContent=d.error||'Failed.';b.disabled=false;b.textContent='Save & Start'}}
catch(e){m.className='msg err';m.textContent='Error: '+e.message;b.disabled=false;b.textContent='Save & Start'}}
document.addEventListener('keydown',e=>{if(e.key==='Enter')go()});
</script>
</body>
</html>
HTMLEOF

# configure-keys.sh CLI tool
cat > "$REAL_HOME/configure-keys.sh" << 'CLIEOF'
#!/bin/bash
set -euo pipefail
VM_ENV="$HOME/controllable-sandbox/config/vm.env"
echo "============================================"
echo " OptimalScale AI Scientist — API Key Setup"
echo "============================================"
read -rp "Enter OPENAI_API_KEY (required): " k1
[ -z "$k1" ] && echo "ERROR: required." && exit 1
read -rp "Enter FIRECRAWL_API_KEY (optional, Enter to skip): " k2
sed -i "s|^OPENAI_API_KEY=.*|OPENAI_API_KEY=${k1}|" "$VM_ENV"
[ -n "$k2" ] && sed -i "s|^FIRECRAWL_API_KEY=.*|FIRECRAWL_API_KEY=${k2}|" "$VM_ENV"
touch "$HOME/.setup-complete"
echo "Restarting services..."
sudo systemctl stop ai-scientists-setup.service 2>/dev/null || true
sudo systemctl restart sandbox-vm.service
sudo systemctl restart ai-scientists-web.service
echo "Done! Open http://localhost:15001"
CLIEOF
chmod +x "$REAL_HOME/configure-keys.sh"

chown -R "$REAL_USER:$REAL_USER" "$SETUP_DIR" "$REAL_HOME/configure-keys.sh"

###############################################################################
# Step 9: Permissions + start services
###############################################################################
step 9 "Configuring permissions and starting services..."

# Passwordless sudo
echo "$REAL_USER ALL=(ALL) NOPASSWD:ALL" > "/etc/sudoers.d/$REAL_USER"
chmod 440 "/etc/sudoers.d/$REAL_USER"

# Remove setup sentinel (ensure setup portal shows on first boot)
rm -f "$REAL_HOME/.setup-complete"

# Start the setup portal
systemctl start ai-scientists-setup.service

echo ""
echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN} Installation complete!${NC}"
echo -e "${GREEN}============================================${NC}"
echo ""
echo " Open in your browser: http://localhost:15001"
echo " Enter your OpenAI API Key, then click Save & Start"
echo ""
echo " SSH access:       ssh -p 2222 $(whoami)@localhost"
echo " Reconfigure keys: ~/configure-keys.sh"
echo ""
