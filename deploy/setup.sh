#!/bin/bash
# ═══════════════════════════════════════════════════════
#  BlockChainT - Sunucu Kurulum Scripti
#  Oracle Cloud Ubuntu 20.04 için
# ═══════════════════════════════════════════════════════
set -e

echo "══════════════════════════════════════"
echo "  BlockChainT Sunucu Kurulumu"
echo "══════════════════════════════════════"

# ── 1. Sistem güncellemesi ────────────────────────
echo "[1/7] Sistem güncelleniyor..."
sudo apt-get update -y
sudo apt-get upgrade -y

# ── 2. Gerekli paketler ──────────────────────────
echo "[2/7] Gerekli paketler kuruluyor..."
sudo apt-get install -y python3 python3-pip python3-venv nginx ufw certbot python3-certbot-nginx

# ── 3. Proje dizini ──────────────────────────────
echo "[3/7] Proje dizini hazırlanıyor..."
sudo mkdir -p /opt/blockchaint
sudo chown ubuntu:ubuntu /opt/blockchaint

# Eğer dosyalar zaten kopyalandıysa, venv oluştur
cd /opt/blockchaint

# ── 4. Python sanal ortam ────────────────────────
echo "[4/7] Python sanal ortam oluşturuluyor..."
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# ── 5. Log dizini ────────────────────────────────
echo "[5/7] Log dizini oluşturuluyor..."
mkdir -p /opt/blockchaint/logs
mkdir -p /opt/blockchaint/data

# ── 6. Systemd servisi ──────────────────────────
echo "[6/7] Systemd servisi kuruluyor..."
sudo cp deploy/blockchain.service /etc/systemd/system/blockchaint.service
sudo systemctl daemon-reload
sudo systemctl enable blockchaint
sudo systemctl start blockchaint

# ── 7. Nginx yapılandırma ────────────────────────
echo "[7/7] Nginx yapılandırılıyor..."
sudo cp deploy/nginx.conf /etc/nginx/sites-available/blockchaint
sudo ln -sf /etc/nginx/sites-available/blockchaint /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl restart nginx

# ── 8. Firewall & SSH Hardening ──────────────────
echo "[EXTRA] Firewall ve SSH güvenliği yapılandırılıyor..."
sudo ufw limit 22/tcp comment 'SSH rate limiting & brute-force defense'
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw --force enable
sudo apt-get install -y fail2ban
sudo systemctl enable fail2ban
sudo systemctl start fail2ban

echo ""
echo "══════════════════════════════════════"
echo "  ✅ Kurulum tamamlandı!"
echo "  API: http://$(curl -s ifconfig.me)/api/v1/stats"
echo "══════════════════════════════════════"

