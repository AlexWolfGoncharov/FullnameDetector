"""Auto-setup module - downloads and installs all required models"""

import os
import sys
import subprocess
import shutil
import logging
import time
from pathlib import Path

import httpx

from app.config import get_settings, MODELS_DIR

logger = logging.getLogger(__name__)


class SetupManager:
    """Manages automatic setup of all dependencies"""

    def __init__(self):
        self.settings = get_settings()
        self._setup_logging()

    def _setup_logging(self):
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )

    def setup_all(self) -> bool:
        """Run complete setup - download all models and dependencies"""
        logger.info("=" * 60)
        logger.info("Starting automatic setup...")
        logger.info("=" * 60)

        success = True

        # 1. Create directories
        self._create_directories()

        # 2. Install spaCy model
        if not self._setup_spacy():
            logger.warning("spaCy setup had issues, continuing...")

        # 3. LLM setup (Ollama or llama.cpp)
        if self.settings.llm_enabled:
            if self.settings.llm_backend == "ollama":
                if not self._setup_ollama():
                    logger.warning("Ollama setup incomplete - will work without LLM fallback")
                    success = False
            else:
                if not self._setup_llm():
                    logger.warning("LLM setup incomplete - will work without LLM fallback")
                    success = False

        logger.info("=" * 60)
        if success:
            logger.info("Setup completed successfully!")
        else:
            logger.info("Setup completed with warnings")
        logger.info("=" * 60)

        return success

    def _create_directories(self):
        """Create necessary directories"""
        MODELS_DIR.mkdir(parents=True, exist_ok=True)
        logger.info(f"Models directory: {MODELS_DIR}")

    def _setup_spacy(self) -> bool:
        """Download and install spaCy Ukrainian model"""
        model_name = self.settings.spacy_model

        logger.info(f"Checking spaCy model: {model_name}")

        try:
            import spacy
            try:
                nlp = spacy.load(model_name)
                logger.info(f"spaCy model '{model_name}' already installed")
                return True
            except OSError:
                pass
        except ImportError:
            logger.error("spaCy not installed. Run: pip install spacy")
            return False

        # Download model
        logger.info(f"Downloading spaCy model: {model_name}")
        try:
            subprocess.run(
                [sys.executable, "-m", "spacy", "download", model_name],
                check=True,
                capture_output=True,
                text=True
            )
            logger.info(f"spaCy model '{model_name}' installed successfully")
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to download spaCy model: {e.stderr}")
            return False

    def _setup_llm(self) -> bool:
        """Download MamayLM GGUF model from HuggingFace"""
        model_path = self.settings.llm_model_path

        if model_path.exists():
            size_gb = model_path.stat().st_size / (1024 ** 3)
            logger.info(f"LLM model already exists: {model_path} ({size_gb:.2f} GB)")
            return True

        logger.info("=" * 50)
        logger.info("Downloading MamayLM model from HuggingFace...")
        logger.info(f"Repository: {self.settings.llm_model_repo}")
        logger.info(f"File: {self.settings.llm_model_file}")
        logger.info(f"Size: ~{self.settings.llm_model_size_mb} MB")
        logger.info(f"Destination: {model_path}")
        logger.info("=" * 50)

        try:
            from huggingface_hub import hf_hub_download, list_repo_files

            # Список доступных файлов для выбора правильной квантованной версии
            try:
                files = list_repo_files(
                    repo_id=self.settings.llm_model_repo,
                    token=self.settings.hf_token
                )
                gguf_files = [f for f in files if f.endswith('.gguf')]
                logger.info(f"Available GGUF files: {gguf_files}")
                
                # Если указанный файл не найден, пробуем найти Q4_K_M версию
                if self.settings.llm_model_file not in files:
                    q4_files = [f for f in gguf_files if 'Q4_K_M' in f or 'q4_k_m' in f]
                    if q4_files:
                        actual_file = q4_files[0]
                        logger.info(f"Using alternative file: {actual_file}")
                    else:
                        # Берем первый GGUF файл
                        actual_file = gguf_files[0] if gguf_files else self.settings.llm_model_file
                        logger.info(f"Using first available GGUF file: {actual_file}")
                else:
                    actual_file = self.settings.llm_model_file
            except Exception as e:
                logger.warning(f"Could not list repo files: {e}, using configured filename")
                actual_file = self.settings.llm_model_file

            # Download with HuggingFace Hub (supports resume, progress, auth)
            downloaded_path = hf_hub_download(
                repo_id=self.settings.llm_model_repo,
                filename=actual_file,
                local_dir=MODELS_DIR,
                local_dir_use_symlinks=False,
                token=self.settings.hf_token if self.settings.hf_token else None
            )

            logger.info(f"Download complete: {downloaded_path}")

            # Verify file exists at expected path
            if model_path.exists():
                size_gb = model_path.stat().st_size / (1024 ** 3)
                logger.info(f"Model ready: {size_gb:.2f} GB")
                return True
            else:
                # File might be in subdirectory or have different name, move/rename it
                downloaded = Path(downloaded_path)
                if downloaded.exists() and downloaded != model_path:
                    import shutil
                    shutil.move(str(downloaded), str(model_path))
                    logger.info(f"Model moved to: {model_path}")
                    return True
                elif downloaded.exists():
                    # File already at correct location
                    return True

            return True

        except ImportError:
            logger.error("huggingface_hub not installed. Installing...")
            try:
                subprocess.run(
                    [sys.executable, "-m", "pip", "install", "huggingface_hub"],
                    check=True,
                    capture_output=True
                )
                # Retry after install
                return self._setup_llm()
            except Exception as e:
                logger.error(f"Failed to install huggingface_hub: {e}")
                return False

        except Exception as e:
            logger.error(f"Failed to download LLM model: {e}")
            if model_path.exists():
                model_path.unlink()
            return False

    def _ollama_is_running(self) -> bool:
        """Check if Ollama server is running"""
        try:
            r = httpx.get(
                f"{self.settings.ollama_base_url}/api/tags",
                timeout=2.0
            )
            return r.status_code == 200
        except Exception:
            return False

    def _ollama_start(self) -> bool:
        """Start Ollama server in background if not running"""
        if self._ollama_is_running():
            return True

        ollama_cmd = shutil.which("ollama")
        if not ollama_cmd:
            logger.warning("ollama not found in PATH. Install from https://ollama.com")
            return False

        logger.info("Starting Ollama server...")
        try:
            # Start ollama serve in background (detached)
            subprocess.Popen(
                [ollama_cmd, "serve"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True
            )
            # Wait for server to be ready
            for _ in range(15):
                time.sleep(1)
                if self._ollama_is_running():
                    logger.info("Ollama server started")
                    return True
            logger.error("Ollama server failed to start within 15 seconds")
            return False
        except Exception as e:
            logger.error(f"Failed to start Ollama: {e}")
            return False

    def _ollama_model_exists(self) -> bool:
        """Check if configured model exists in Ollama"""
        try:
            r = httpx.get(
                f"{self.settings.ollama_base_url}/api/tags",
                timeout=5.0
            )
            if r.status_code != 200:
                return False
            models = r.json().get("models", [])
            model_base = self.settings.ollama_model.split(":")[0]
            return any(
                m.get("name", "").startswith(model_base)
                for m in models
            )
        except Exception:
            return False

    def _setup_ollama(self) -> bool:
        """Ensure Ollama is running and model is available"""
        # 1. Start Ollama if not running
        if not self._ollama_start():
            return False

        # 2. Check if model exists
        if self._ollama_model_exists():
            logger.info(f"Ollama model '{self.settings.ollama_model}' already available")
            return True

        # 3. Model not in Ollama — create from GGUF
        model_path = self.settings.llm_model_path

        if not model_path.exists():
            logger.info("GGUF not found, downloading for Ollama...")
            if not self._setup_llm():
                logger.error("Failed to download GGUF for Ollama")
                return False

        # 4. Create Modelfile and ollama create
        model_base = self.settings.ollama_model.split(":")[0]
        modelfile_path = MODELS_DIR / "Modelfile.mamaylm"

        try:
            modelfile_content = f"""FROM {model_path.absolute()}
PARAMETER temperature 0.1
PARAMETER num_ctx 2048
"""
            modelfile_path.write_text(modelfile_content, encoding="utf-8")
            logger.info(f"Created Modelfile at {modelfile_path}")

            logger.info(f"Creating Ollama model '{model_base}' from GGUF (may take a minute)...")
            result = subprocess.run(
                ["ollama", "create", model_base, "-f", str(modelfile_path)],
                capture_output=True,
                text=True,
                timeout=300
            )

            if result.returncode != 0:
                logger.error(f"ollama create failed: {result.stderr}")
                return False

            logger.info(f"Ollama model '{model_base}' created successfully")
            return True

        except subprocess.TimeoutExpired:
            logger.error("ollama create timed out")
            return False
        except FileNotFoundError:
            logger.error("ollama command not found. Install from https://ollama.com")
            return False
        except Exception as e:
            logger.error(f"Ollama setup failed: {e}")
            return False

    def verify_setup(self) -> dict:
        """Verify all components are properly set up"""
        status = {
            "spacy_model": False,
            "llm_model": False,
            "llm_loadable": False
        }

        # Check spaCy
        try:
            import spacy
            nlp = spacy.load(self.settings.spacy_model)
            status["spacy_model"] = True
            logger.info(f"spaCy model OK: {self.settings.spacy_model}")
        except Exception as e:
            logger.error(f"spaCy model check failed: {e}")

        # Check LLM (Ollama or llama.cpp)
        if self.settings.llm_backend == "ollama":
            status["llm_model"] = self._ollama_is_running()
            status["llm_loadable"] = status["llm_model"] and self._ollama_model_exists()
            if status["llm_model"]:
                logger.info("Ollama: running")
            else:
                logger.warning("Ollama: not running")
            if status["llm_loadable"]:
                logger.info("Ollama model: available")
            else:
                logger.warning("Ollama model: not found")
        else:
            model_path = self.settings.llm_model_path
            if model_path.exists():
                size_gb = model_path.stat().st_size / (1024 ** 3)
                status["llm_model"] = True
                logger.info(f"LLM model file OK: {model_path} ({size_gb:.2f} GB)")

                try:
                    from llama_cpp import Llama
                    logger.info("Testing LLM load (this may take a moment)...")
                    llm = Llama(
                        model_path=str(model_path),
                        n_ctx=512,
                        n_threads=2,
                        verbose=False
                    )
                    del llm
                    status["llm_loadable"] = True
                    logger.info("LLM model loadable: OK")
                except Exception as e:
                    logger.error(f"LLM load test failed: {e}")
            else:
                logger.warning(f"LLM model not found: {model_path}")

        return status


def run_setup():
    """Run setup from command line"""
    manager = SetupManager()
    manager.setup_all()
    status = manager.verify_setup()

    print("\n" + "=" * 40)
    print("Setup Status:")
    print("=" * 40)
    for component, ok in status.items():
        emoji = "[OK]" if ok else "[MISSING]"
        print(f"  {emoji} {component}")
    print("=" * 40)

    if all(status.values()):
        print("\nAll components ready! Run the API with:")
        print("  python run.py")
    else:
        print("\nSome components missing. Check errors above.")


if __name__ == "__main__":
    run_setup()
