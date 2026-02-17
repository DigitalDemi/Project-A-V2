#!/bin/bash

# Download LLM model script
# Downloads quantized Qwen 2.5 3B for local inference

set -e

MODEL_URL="https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF/resolve/main/qwen2.5-3b-instruct-q4_k_m.gguf"
MODEL_DIR="agent-service/models"
MODEL_FILE="qwen2.5-3b-instruct-q4_k_m.gguf"

echo "📥 Downloading Qwen 2.5 3B Instruct (Q4_K_M quantization)..."
echo "This model is ~2GB and runs efficiently on CPU"
echo ""

mkdir -p $MODEL_DIR

if [ -f "$MODEL_DIR/$MODEL_FILE" ]; then
    echo "✅ Model already exists at $MODEL_DIR/$MODEL_FILE"
    exit 0
fi

# Check if curl is available
if ! command -v curl &> /dev/null; then
    echo "❌ curl is required but not installed"
    exit 1
fi

# Download with progress
echo "Downloading from HuggingFace..."
curl -L --progress-bar "$MODEL_URL" -o "$MODEL_DIR/$MODEL_FILE"

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ Model downloaded successfully!"
    echo "Location: $MODEL_DIR/$MODEL_FILE"
    echo "Size: $(du -h $MODEL_DIR/$MODEL_FILE | cut -f1)"
else
    echo ""
    echo "❌ Download failed"
    exit 1
fi
