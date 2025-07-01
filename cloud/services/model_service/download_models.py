import os
import logging
from transformers import AutoModelForSeq2SeqLM, AutoTokenizer, AutoModelForCausalLM

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

# Set cache directory
os.environ["HF_HOME"] = os.getenv("HF_HOME", "/model_cache")

models = [
    #"google/flan-t5-large",
    #"facebook/bart-large-cnn",
    "microsoft/Phi-3-mini-4k-instruct",  # Or "google/flan-t5-large" or "facebook/bart-large-cnn"
    #"meta-llama/Llama-3-8B-Instruct"  # Or "mistralai/Mixtral-8x7B-Instruct-v0.1"
]

for model_name in models:
    logger.info(f"Downloading {model_name}...")
    try:
        token = os.getenv("HF_TOKEN") if "llama" in model_name.lower() else None
        if "llama" in model_name.lower() or "mixtral" in model_name.lower():
            model = AutoModelForCausalLM.from_pretrained(model_name, cache_dir=os.environ["HF_HOME"], token=token)
            tokenizer = AutoTokenizer.from_pretrained(model_name, cache_dir=os.environ["HF_HOME"], token=token)
        else:
            model = AutoModelForSeq2SeqLM.from_pretrained(model_name, cache_dir=os.environ["HF_HOME"])
            tokenizer = AutoTokenizer.from_pretrained(model_name, cache_dir=os.environ["HF_HOME"])
        logger.info(f"{model_name} downloaded and cached successfully")
    except Exception as e:
        logger.error(f"Error downloading {model_name}: {e}")

# Verify cache
os.system(f"ls -l {os.environ['HF_HOME']}/hub")