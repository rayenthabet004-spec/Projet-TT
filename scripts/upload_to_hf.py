"""
upload_to_hf.py - Push trained multi_engine_t5_model to Hugging Face Hub

Usage:
  1. pip install huggingface_hub
  2. huggingface-cli login
  3. python scripts/upload_to_hf.py --repo_id "rayenthabet004/tt-multi-engine-t5"
"""

import os
import sys
import argparse

def main():
    parser = argparse.ArgumentParser(description="Upload trained T5 model to Hugging Face Hub")
    parser.add_argument(
        "--model_dir",
        type=str,
        default=os.path.join(os.path.dirname(__file__), "..", "models", "multi_engine_t5_model"),
        help="Path to local trained model directory"
    )
    parser.add_argument(
        "--repo_id",
        type=str,
        default="rayenthabet004/tt-multi-engine-t5",
        help="Hugging Face repo ID (e.g. username/repo-name)"
    )
    parser.add_argument(
        "--private",
        action="store_true",
        help="Create private repository"
    )

    args = parser.parse_args()

    model_dir = os.path.abspath(args.model_dir)
    if not os.path.isdir(model_dir):
        print(f"Error: Model directory not found at {model_dir}")
        sys.exit(1)

    try:
        from huggingface_hub import HfApi
    except ImportError:
        print("Please install huggingface_hub: pip install huggingface_hub")
        sys.exit(1)

    print(f"Uploading model from {model_dir} to Hugging Face Hub repo '{args.repo_id}'...")
    api = HfApi()
    api.create_repo(repo_id=args.repo_id, private=args.private, exist_ok=True)
    api.upload_folder(
        folder_path=model_dir,
        repo_id=args.repo_id,
        repo_type="model"
    )
    print(f"Success! Model uploaded to https://huggingface.co/{args.repo_id}")

if __name__ == "__main__":
    main()
