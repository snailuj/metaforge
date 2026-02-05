terraform {
  required_version = ">= 1.5.0"

  required_providers {
    vultr = {
      source  = "vultr/vultr"
      version = "~> 2.19"
    }
  }
}

provider "vultr" {
  # API key from VULTR_API_KEY environment variable
}

# -----------------------------------------------------------------------------
# Variables
# -----------------------------------------------------------------------------

variable "ssh_public_key" {
  description = "SSH public key content for agent user access"
  type        = string
}

variable "region" {
  description = "Vultr region ID"
  type        = string
  default     = "lhr" # London
}

variable "plan" {
  description = "Vultr plan ID (2 vCPU / 4GB RAM)"
  type        = string
  default     = "vc2-2c-4gb"
}

variable "hostname" {
  description = "Instance hostname"
  type        = string
  default     = "metaforge-agent"
}

# -----------------------------------------------------------------------------
# SSH Key
# -----------------------------------------------------------------------------

resource "vultr_ssh_key" "agent" {
  name    = "metaforge-agent-key"
  ssh_key = var.ssh_public_key
}

# -----------------------------------------------------------------------------
# Startup Script (cloud-init)
# -----------------------------------------------------------------------------

resource "vultr_startup_script" "agent_setup" {
  name   = "metaforge-agent-setup"
  type   = "boot"
  script = base64encode(file("${path.module}/cloud-init.sh"))
}

# -----------------------------------------------------------------------------
# Instance
# -----------------------------------------------------------------------------

resource "vultr_instance" "agent" {
  label     = var.hostname
  hostname  = var.hostname
  region    = var.region
  plan      = var.plan
  os_id     = 2284 # Ubuntu 24.04 LTS x64

  ssh_key_ids = [vultr_ssh_key.agent.id]
  script_id   = vultr_startup_script.agent_setup.id

  backups         = "disabled"
  enable_ipv6     = true
  ddos_protection = false

  tags = ["metaforge", "agent", "dev"]
}

# -----------------------------------------------------------------------------
# Outputs
# -----------------------------------------------------------------------------

output "instance_ip" {
  description = "Public IPv4 address"
  value       = vultr_instance.agent.main_ip
}

output "instance_ipv6" {
  description = "Public IPv6 address"
  value       = vultr_instance.agent.v6_main_ip
}

output "instance_id" {
  description = "Vultr instance ID (for snapshots)"
  value       = vultr_instance.agent.id
}

output "ssh_command" {
  description = "SSH command to connect"
  value       = "ssh agent@${vultr_instance.agent.main_ip}"
}
