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
sudo apt-get install -y python3 python3-pip python3-venv nginx ufw certbot python3-certbot-nginx cargo rustc build-essential

# ── 3. Proje dizini ──────────────────────────────
echo "[3/7] Proje dizini hazırlanıyor..."
sudo mkdir -p /opt/blockchaint
sudo chown ubuntu:ubuntu /opt/blockchaint

# Eğer dosyalar zaten kopyalandıysa, venv oluştur
cd /opt/blockchaint

# ── 4. Python sanal ortam & Rust Çekirdeği ───────
echo "[4/7] Python sanal ortam oluşturuluyor ve bağımlılıklar kuruluyor..."
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# AUD14-05: Rust Core Native Acceleration Build via maturin
echo "  -> Rust çekirdeği (locktrace_core) derleniyor..."
if command -v cargo >/dev/null 2>&1; then
    pip install maturin
    (cd /opt/blockchaint/crates/locktrace_core && maturin develop --release) || echo "  [UYARI] maturin derlemesi başarısız, Python fallback devrede kalacak."
else
    echo "  [BİLGİ] Cargo bulunamadı, Rust çekirdeği atlanıyor (saf Python fallback etkin)."
fi

# ── 5. Log dizini ve Gizli Anahtarlar (.env) ─────
echo "[5/7] Log dizini ve güvenli .env hazırlanıyor..."
mkdir -p /opt/blockchaint/logs
mkdir -p /opt/blockchaint/data

if [ ! -f /opt/blockchaint/.env ]; then
    SECRET_HEX=$(python3 -c "import secrets; print(secrets.token_hex(32))")
    ADMIN_HEX=$(python3 -c "import secrets; print(secrets.token_hex(32))")
    (
        umask 077
        cat <<EOF > /opt/blockchaint/.env
BCT_SECRET_KEY=${SECRET_HEX}
BCT_ADMIN_KEY=${ADMIN_HEX}
BCT_DEBUG=false
BCT_LOG_LEVEL=INFO
EOF
    )
    chmod 600 /opt/blockchaint/.env
    chown ubuntu:ubuntu /opt/blockchaint/.env
    echo "  -> Yeni 256-bit kriptografik .env oluşturuldu ve kilitlendi (chmod 600, umask 077)."
fi

# ── 6. Systemd servisi ──────────────────────────
echo "[6/7] Systemd servisi kuruluyor..."
sudo cp deploy/blockchain.service /etc/systemd/system/blockchaint.service
sudo systemctl daemon-reload
sudo systemctl enable blockchaint
sudo systemctl restart blockchaint

# ── 7. Nginx yapılandırma ────────────────────────
echo "[7/7] Nginx yapılandırılıyor..."
if [ -f "/etc/letsencrypt/live/www.locktrace.space/fullchain.pem" ] || [ -f "/etc/letsencrypt/live/locktrace.space/fullchain.pem" ]; then
    echo "  -> Let's Encrypt SSL sertifikaları tespit edildi. deploy/nginx_ssl.conf kuruluyor..."
    sudo cp deploy/nginx_ssl.conf /etc/nginx/sites-available/blockchaint
else
    echo "  -> SSL sertifikası bulunamadı. Tam özellikli HTTP yapılandırması (deploy/nginx.conf) kuruluyor..."
    sudo cp deploy/nginx.conf /etc/nginx/sites-available/blockchaint
fi
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
echo "  Canlı API: https://www.locktrace.space/api/v1/stats"
echo "  Yerel API: http://$(curl -s ifconfig.me)/api/v1/stats"
echo "══════════════════════════════════════"

