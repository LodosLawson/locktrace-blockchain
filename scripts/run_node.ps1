# =====================================================================
# LockTrace Decentralized Node & Verified Web Launcher (Windows)
# =====================================================================
Write-Host "=== LockTrace Decentralized Node & Web Setup (v2.9.0) ===" -ForegroundColor Cyan

$pyCmd = Get-Command python -ErrorAction SilentlyContinue
if (!$pyCmd) { $pyCmd = Get-Command py -ErrorAction SilentlyContinue }
if (!$pyCmd) {
    Write-Error "Python 3 bulunamadi. Lutfen https://python.org adresinden yukleyin."
    exit 1
}

$name = Read-Host "Dugum Adi (orn: Windows-Peer-01)"
if ([string]::IsNullOrWhiteSpace($name)) { $name = "Windows-Community-Peer" }

$loc = Read-Host "Konum (orn: Istanbul, TR)"
if ([string]::IsNullOrWhiteSpace($loc)) { $loc = "Global" }

Write-Host ""
Write-Host "Frontend Calisma Modunu Secin:" -ForegroundColor Yellow
Write-Host "  [1] Yerel Mod (Sadece bu bilgisayarda ac: http://127.0.0.1:5050 + Tarayiciyi Ac)"
Write-Host "  [2] Sunucu Modu (Agda / Internette sunucu olarak ac: http://0.0.0.0:5050)"
Write-Host "  [3] Sadece P2P Madenci/Dogrulayici (Web arayuzu kapali)"
$mode = Read-Host "Seciminiz (Varsayilan: 1)"

if ($mode -eq "2") {
    & $pyCmd.Source node_runner.py --name "$name" --location "$loc" --server --port 5050
} elseif ($mode -eq "3") {
    & $pyCmd.Source node_runner.py --name "$name" --location "$loc" --no-web
} else {
    & $pyCmd.Source node_runner.py --name "$name" --location "$loc" --local --open
}
