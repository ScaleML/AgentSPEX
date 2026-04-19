packer {
  required_plugins {
    virtualbox = {
      version = ">= 1.1.1"
      source  = "github.com/hashicorp/virtualbox"
    }
  }
}

variable "version" {
  type    = string
  default = "1.0.0"
}

variable "iso_url" {
  type    = string
  default = "https://releases.ubuntu.com/22.04.5/ubuntu-22.04.5-live-server-amd64.iso"
}

variable "iso_checksum" {
  type    = string
  default = "sha256:9bc6028870aef3f74f4e16b900008179e78b130e6b0b9a140635434a46aa98b0"
}

variable "cpus" {
  type    = number
  default = 4
}

variable "memory" {
  type    = number
  default = 8192
}

variable "disk_size" {
  type    = number
  default = 65536
}

variable "ssh_username" {
  type    = string
  default = "aiscientist"
}

variable "ssh_password" {
  type    = string
  default = "aiscientist"
}

variable "output_directory" {
  type    = string
  default = "../output"
}

source "virtualbox-iso" "ai-scientists" {
  guest_os_type = "Ubuntu_64"
  vm_name       = "AI-Scientists-v${var.version}"

  iso_url      = var.iso_url
  iso_checksum = var.iso_checksum

  cpus             = var.cpus
  memory           = var.memory
  disk_size        = var.disk_size
  hard_drive_interface = "sata"

  ssh_username = var.ssh_username
  ssh_password = var.ssh_password
  ssh_timeout  = "60m"

  headless = true

  http_directory = "http"

  # Ubuntu 22.04 autoinstall boot command
  boot_wait = "30s"
  boot_command = [
    "c<wait5>",
    "linux /casper/vmlinuz --- autoinstall ds='nocloud-net;s=http://{{ .HTTPIP }}:{{ .HTTPPort }}/' ",
    "<enter><wait5>",
    "initrd /casper/initrd",
    "<enter><wait5>",
    "boot",
    "<enter>"
  ]

  shutdown_command = "echo '${var.ssh_password}' | sudo -S shutdown -P now"
  format          = "ova"

  output_directory = var.output_directory
  output_filename  = "ai-scientists-v${var.version}"

  # NAT port forwarding rules
  vboxmanage = [
    ["modifyvm", "{{ .Name }}", "--nat-localhostreachable1", "on"],
    ["modifyvm", "{{ .Name }}", "--natpf1", "flask,tcp,,5001,,5001"],
    ["modifyvm", "{{ .Name }}", "--natpf1", "vnc,tcp,,6080,,6080"],
    ["modifyvm", "{{ .Name }}", "--natpf1", "ssh,tcp,,2222,,22"]
  ]

  # Guest additions not needed for headless server
  guest_additions_mode = "disable"
}

build {
  sources = ["source.virtualbox-iso.ai-scientists"]

  # Upload project files and service configs
  provisioner "file" {
    source      = "files/"
    destination = "/tmp/packer-files"
  }

  # Provisioning scripts (run in order)
  provisioner "shell" {
    scripts = [
      "scripts/01-base-system.sh",
      "scripts/02-docker.sh",
      "scripts/03-conda.sh",
      "scripts/04-latex.sh",
      "scripts/05-project.sh",
      "scripts/06-docker-image.sh",
      "scripts/07-services.sh",
      "scripts/08-setup-portal.sh",
      "scripts/09-cleanup.sh"
    ]
    execute_command  = "echo '${var.ssh_password}' | sudo -S bash -euxo pipefail '{{ .Path }}'"
    expect_disconnect = true
  }
}
