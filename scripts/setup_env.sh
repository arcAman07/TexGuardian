#!/bin/bash
# TexGuardian Environment Setup Script
# Source this script to set up the environment for testing
#
# SECURITY: This script does NOT contain credentials.
# Credentials are loaded from ~/.texguardian/credentials (gitignored)

set -e

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
CREDENTIALS_FILE="$HOME/.texguardian/credentials"

# Activate virtual environment
if [ -d "$PROJECT_ROOT/.venv" ]; then
    source "$PROJECT_ROOT/.venv/bin/activate"
    echo "✓ Activated virtual environment"
else
    echo "Creating virtual environment..."
    python -m venv "$PROJECT_ROOT/.venv"
    source "$PROJECT_ROOT/.venv/bin/activate"
    pip install -e "$PROJECT_ROOT[dev]"
    echo "✓ Created and activated virtual environment"
fi

# Load credentials from secure location
if [ -f "$CREDENTIALS_FILE" ]; then
    source "$CREDENTIALS_FILE"
    echo "✓ Loaded credentials from $CREDENTIALS_FILE"
else
    echo ""
    echo "⚠️  Credentials file not found: $CREDENTIALS_FILE"
    echo ""
    echo "To set up credentials, create the file with:"
    echo ""
    echo "  mkdir -p ~/.texguardian"
    echo "  cat > ~/.texguardian/credentials << 'EOF'"
    echo "  export AWS_ACCESS_KEY_ID=\"your-access-key\""
    echo "  export AWS_SECRET_ACCESS_KEY=\"your-secret-key\""
    echo "  export AWS_REGION=\"us-east-1\""
    echo "  EOF"
    echo "  chmod 600 ~/.texguardian/credentials"
    echo ""
    echo "Or use an AWS profile by adding to the file:"
    echo "  export AWS_PROFILE=\"your-profile-name\""
    echo ""
fi

# Add TinyTeX to PATH if installed
TINYTEX_BIN="$HOME/Library/TinyTeX/bin/universal-darwin"
if [ -d "$TINYTEX_BIN" ]; then
    export PATH="$TINYTEX_BIN:$PATH"
    echo "✓ Added TinyTeX to PATH"
fi

# Add MacTeX to PATH if installed
if [ -d "/Library/TeX/texbin" ]; then
    export PATH="/Library/TeX/texbin:$PATH"
    echo "✓ Added MacTeX to PATH"
fi

# Default model configuration (safe to commit)
export TEXGUARDIAN_DEFAULT_MODEL="${TEXGUARDIAN_DEFAULT_MODEL:-claude opus 4.5}"
export TEXGUARDIAN_MAX_OUTPUT_TOKENS="${TEXGUARDIAN_MAX_OUTPUT_TOKENS:-32000}"
export TEXGUARDIAN_MAX_THINKING_TOKENS="${TEXGUARDIAN_MAX_THINKING_TOKENS:-16000}"

echo ""
echo "Environment configured:"
echo "  AWS_REGION=${AWS_REGION:-not set}"
echo "  AWS_PROFILE=${AWS_PROFILE:-not set}"
echo "  Model: $TEXGUARDIAN_DEFAULT_MODEL"
echo "  Max Output Tokens: $TEXGUARDIAN_MAX_OUTPUT_TOKENS"
echo "  Max Thinking Tokens: $TEXGUARDIAN_MAX_THINKING_TOKENS"
echo ""
echo "To test TexGuardian:"
echo "  cd $PROJECT_ROOT/examples/position_paper"
echo "  texguardian chat"
