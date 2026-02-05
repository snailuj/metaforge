# Example terraform.tfvars
# Copy to terraform.tfvars and fill in your values

# Your SSH public key (required)
# ssh_public_key = "ssh-ed25519 AAAA... user@host"

# Vultr region (default: London)
# region = "lhr"

# Available regions:
#   lhr - London
#   ams - Amsterdam
#   fra - Frankfurt
#   par - Paris
#   ewr - New Jersey
#   ord - Chicago
#   dfw - Dallas
#   lax - Los Angeles
#   sfo - Silicon Valley
#   sgp - Singapore
#   nrt - Tokyo
#   syd - Sydney

# Instance plan (default: 2 vCPU / 4GB RAM)
# plan = "vc2-2c-4gb"

# Available plans:
#   vc2-1c-1gb  - 1 vCPU / 1GB RAM  (~$6/mo)
#   vc2-1c-2gb  - 1 vCPU / 2GB RAM  (~$12/mo)
#   vc2-2c-4gb  - 2 vCPU / 4GB RAM  (~$24/mo)
#   vc2-4c-8gb  - 4 vCPU / 8GB RAM  (~$48/mo)
#   vc2-6c-16gb - 6 vCPU / 16GB RAM (~$96/mo)

# Hostname
# hostname = "metaforge-agent"
