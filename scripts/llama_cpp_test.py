#!/usr/bin/env python3
"""Test script to verify llama_cpp works with the model.

Usage: python scripts/llama_cpp_test.py
"""

import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def test_model_exists():
    """Check if model file exists"""
    from app.config import get_settings
    settings = get_settings()

    model_path = settings.llm_model_path
    print(f"Model path: {model_path}")
    print(f"Model exists: {model_path.exists()}")

    if model_path.exists():
        size_mb = model_path.stat().st_size / (1024 * 1024)
        print(f"Model size: {size_mb:.1f} MB")

    return model_path.exists()


def test_llama_cpp_import():
    """Test if llama_cpp can be imported"""
    try:
        from llama_cpp import Llama
        print("✓ llama_cpp imported successfully")
        return True
    except ImportError as e:
        print(f"✗ Failed to import llama_cpp: {e}")
        return False


def test_llama_cpp_load():
    """Test loading the model"""
    from app.config import get_settings
    settings = get_settings()

    model_path = settings.llm_model_path
    if not model_path.exists():
        print(f"✗ Model not found at: {model_path}")
        return None

    try:
        from llama_cpp import Llama

        print(f"Loading model from: {model_path}")
        print("This may take a moment...")

        llm = Llama(
            model_path=str(model_path),
            n_ctx=2048,
            n_threads=2,
            verbose=True
        )

        print("✓ Model loaded successfully!")
        return llm

    except Exception as e:
        print(f"✗ Failed to load model: {e}")
        import traceback
        traceback.print_exc()
        return None


def main():
    print("=" * 60)
    print("llama_cpp Test Suite")
    print("=" * 60)

    print("\n[1] Checking model file...")
    model_exists = test_model_exists()

    print("\n[2] Testing llama_cpp import...")
    import_ok = test_llama_cpp_import()

    if not import_ok:
        print("\nInstall: pip install llama-cpp-python")
        return

    if not model_exists:
        print("\nModel not found. Run: python run.py --setup-only")
        return

    print("\n[3] Loading model...")
    llm = test_llama_cpp_load()
    if llm:
        print("\n✓ All tests passed!")


if __name__ == "__main__":
    main()
