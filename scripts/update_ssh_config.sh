#!/bin/bash
# ─────────────────────────────────────────────────────────────
# update_ssh_config.sh
#
# Updates your SSH config with the current Bastion IP AND the
# current App EC2 (blue) private IP. Both change every session
# since terraform destroy + apply assigns new IPs each time.
#
# Run after every terraform apply.
#
# Usage: bash scripts/update_ssh_config.sh
# ─────────────────────────────────────────────────────────────
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TF_DIR="$(cd "$SCRIPT_DIR/../terraform" && pwd)"

BASTION_IP=$(cd "$TF_DIR" && terraform output -raw bastion_public_ip)
APP_BLUE_IP=$(cd "$TF_DIR" && terraform output -raw app_blue_private_ip)

cat > ~/.ssh/shimonvault_config << EOF
# ShimonVault SSH config — auto-generated, do not edit manually
# Run 'bash scripts/update_ssh_config.sh' after terraform apply
Host shimonvault-bastion
  HostName ${BASTION_IP}
  User ec2-user
  IdentityFile ~/.ssh/id_ed25519_shimonvault
  StrictHostKeyChecking no
  ServerAliveInterval 60

# Jump through bastion to reach private subnet instances
# Usage: ssh shimonvault-app
Host shimonvault-app
  HostName ${APP_BLUE_IP}
  User ec2-user
  IdentityFile ~/.ssh/id_ed25519_shimonvault
  ProxyJump shimonvault-bastion
  StrictHostKeyChecking no
EOF

# Make sure the main SSH config includes our shimonvault config
if ! grep -q "Include ~/.ssh/shimonvault_config" ~/.ssh/config 2>/dev/null; then
  echo "Include ~/.ssh/shimonvault_config" >> ~/.ssh/config
  echo "✅ Added Include to ~/.ssh/config"
fi

echo "✅ SSH config updated."
echo "   Bastion IP:   ${BASTION_IP}"
echo "   App Blue IP:  ${APP_BLUE_IP}"
echo "   Connect to bastion: ssh shimonvault-bastion"
echo "   Connect to app:     ssh shimonvault-app"