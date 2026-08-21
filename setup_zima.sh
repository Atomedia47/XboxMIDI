#!/usr/bin/env bash
# ============================================================
#  ZIMA SERVER SETUP — Knowledge Archive + Multi-Bot System
# ============================================================
#
# Run this on the ZIMA server to set up everything:
#   chmod +x setup_zima.sh && ./setup_zima.sh
#
# What it does:
#   1. Installs dependencies (ollama, aria2c, kiwix-serve, python3)
#   2. Mounts / verifies the WD Black 8TB drive
#   3. Creates the archive directory structure
#   4. Pulls a default local model for the agents
#   5. Starts the multi-bot monitor server
#   6. Starts kiwix-serve for offline Wikipedia access
#
# After running, open http://<zima-ip>:7777 on your phone

set -e

echo "============================================="
echo "  ZIMA SERVER SETUP"
echo "  Knowledge Archive + Multi-Bot System"
echo "============================================="
echo ""

# --- Detect package manager ---
if command -v apt-get &>/dev/null; then
    PKG="apt-get"
    INSTALL="sudo apt-get install -y"
    UPDATE="sudo apt-get update"
elif command -v dnf &>/dev/null; then
    PKG="dnf"
    INSTALL="sudo dnf install -y"
    UPDATE="sudo dnf check-update || true"
elif command -v pacman &>/dev/null; then
    PKG="pacman"
    INSTALL="sudo pacman -S --noconfirm"
    UPDATE="sudo pacman -Sy"
else
    echo "WARNING: Unknown package manager. Install dependencies manually."
    PKG="unknown"
fi

# --- Install system deps ---
echo "[1/6] Installing dependencies..."
if [ "$PKG" != "unknown" ]; then
    $UPDATE
    $INSTALL python3 python3-pip aria2 wget curl git
fi

# --- Install ollama ---
echo ""
echo "[2/6] Setting up Ollama (local LLM runtime)..."
if ! command -v ollama &>/dev/null; then
    echo "  Installing ollama..."
    curl -fsSL https://ollama.com/install.sh | sh
else
    echo "  Ollama already installed: $(ollama --version)"
fi

# Start ollama service
if ! pgrep -x ollama &>/dev/null; then
    echo "  Starting ollama service..."
    ollama serve &>/dev/null &
    sleep 3
fi

# --- Pull default model ---
echo ""
echo "[3/6] Pulling default model (llama3 8B)..."
ollama pull llama3 || echo "  WARNING: Could not pull llama3. Check internet connection."

# --- Set up WD Black 8TB ---
echo ""
echo "[4/6] Setting up archive drive..."
DRIVE_MOUNT="/mnt/wd-black-8tb"
ARCHIVE_DIR="$DRIVE_MOUNT/knowledge-archive"

# Check if drive is mounted
if mountpoint -q "$DRIVE_MOUNT" 2>/dev/null; then
    echo "  Drive mounted at $DRIVE_MOUNT"
else
    echo "  Drive not mounted at $DRIVE_MOUNT"
    echo ""
    echo "  To find and mount your WD Black 8TB:"
    echo "    1. Find the drive:  lsblk -o NAME,SIZE,FSTYPE,MOUNTPOINT"
    echo "    2. Create mount:    sudo mkdir -p $DRIVE_MOUNT"
    echo "    3. Mount it:        sudo mount /dev/sdX1 $DRIVE_MOUNT"
    echo "    4. For auto-mount, add to /etc/fstab:"
    echo "       UUID=<drive-uuid> $DRIVE_MOUNT ext4 defaults,nofail 0 2"
    echo ""
    echo "  Get UUID with: sudo blkid"
    echo ""

    # Create mount point anyway for the directory structure
    sudo mkdir -p "$DRIVE_MOUNT" 2>/dev/null || true
fi

# Create archive directory structure
echo "  Creating archive directories..."
mkdir -p "$ARCHIVE_DIR/01-wikipedia"
mkdir -p "$ARCHIVE_DIR/02-survival"
mkdir -p "$ARCHIVE_DIR/03-cyber"
mkdir -p "$ARCHIVE_DIR/04-infrastructure"
mkdir -p "$ARCHIVE_DIR/05-technical"
mkdir -p "$ARCHIVE_DIR/06-maps-data"
mkdir -p "$ARCHIVE_DIR/07-ai-models"
echo "  Archive root: $ARCHIVE_DIR"

# --- Install kiwix-serve ---
echo ""
echo "[5/6] Setting up Kiwix (offline Wikipedia viewer)..."
if ! command -v kiwix-serve &>/dev/null; then
    echo "  Installing kiwix-tools..."
    if [ "$PKG" = "apt-get" ]; then
        $INSTALL kiwix-tools 2>/dev/null || {
            echo "  Downloading kiwix-tools binary..."
            KIWIX_VER="3.7.0"
            ARCH=$(uname -m)
            case "$ARCH" in
                x86_64)  KIWIX_ARCH="x86_64" ;;
                aarch64) KIWIX_ARCH="aarch64" ;;
                *)       KIWIX_ARCH="$ARCH" ;;
            esac
            wget -q "https://download.kiwix.org/release/kiwix-tools/kiwix-tools_linux-${KIWIX_ARCH}-${KIWIX_VER}.tar.gz" -O /tmp/kiwix.tar.gz
            tar xzf /tmp/kiwix.tar.gz -C /usr/local/bin/ --strip-components=1
            rm /tmp/kiwix.tar.gz
        }
    fi
else
    echo "  Kiwix already installed"
fi

# --- Start services ---
echo ""
echo "[6/6] Starting services..."

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Start multi-bot monitor
echo "  Starting Multi-Bot Monitor on port 7777..."
cd "$SCRIPT_DIR"
python3 run_agents.py --port 7777 &
MONITOR_PID=$!
echo "  Monitor PID: $MONITOR_PID"

# Start kiwix if ZIM files exist
ZIM_FILES=$(find "$ARCHIVE_DIR/01-wikipedia" -name "*.zim" 2>/dev/null | head -5)
if [ -n "$ZIM_FILES" ]; then
    echo "  Starting Kiwix-serve on port 8888..."
    kiwix-serve --port 8888 $ZIM_FILES &
    KIWIX_PID=$!
    echo "  Kiwix PID: $KIWIX_PID"
fi

# --- Get local IP ---
LOCAL_IP=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "localhost")

echo ""
echo "============================================="
echo "  SETUP COMPLETE"
echo "============================================="
echo ""
echo "  Multi-Bot Monitor:  http://$LOCAL_IP:7777"
echo "  Ollama API:         http://$LOCAL_IP:11434"
if [ -n "$ZIM_FILES" ]; then
    echo "  Wikipedia (Kiwix):  http://$LOCAL_IP:8888"
fi
echo ""
echo "  Archive drive:      $ARCHIVE_DIR"
echo ""
echo "  Next steps:"
echo "    1. Open http://$LOCAL_IP:7777 on your phone"
echo "    2. Start downloading: python3 -m archive.downloader --priority 1"
echo "    3. For everything:    python3 -m archive.downloader"
echo ""
echo "  Quick commands:"
echo "    python3 -m archive.downloader --dry-run         # See what will download"
echo "    python3 -m archive.downloader --category wikipedia  # Just Wikipedia"
echo "    python3 -m archive.downloader --priority 1      # Critical items only"
echo "    python3 -m archive.indexer                      # Re-index the archive"
echo ""
echo "  Press Ctrl+C to stop services."
echo ""

wait
