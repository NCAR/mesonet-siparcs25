from transformers import pipeline, AutoTokenizer, AutoModelForSeq2SeqLM, AutoModelForCausalLM
import torch
import logging
import os

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

# Use cache directory from environment variable
CACHE_DIR = os.getenv("HF_HOME", "/model_cache")

class SensorModel:
    def __init__(self):
        pass

    def predict(self, data):
        raise NotImplementedError

    def format_sensor_data(self, data):
        if not data:
            logger.warning("Empty sensor data received")
            return "Act as a weathercaster and describe the environmental conditions. There is no sensor data available."

        prompt = []
        for sensor, measurements in data.items():
            values = ", ".join(f"{k}: {v}" for k, v in measurements.items())
            prompt.append(f"{sensor.capitalize()} sensor readings — {values}")
        
        return (
            "You are a weathercaster. Based on the following sensor data, give a friendly weather report that a person with no knowledge of atmospheric data will understand. Avoid using terms or measurements that people may not understand, "
            "interpret the conditions, and offer practical advice for today: "
            + " | ".join(prompt)
        )


class Phi3MiniModel(SensorModel):
    def __init__(self):
        logger.info("Initializing Phi3MiniModel...")
        self.tokenizer = AutoTokenizer.from_pretrained("microsoft/Phi-3-mini-4k-instruct", local_files_only=True)
        self.model = AutoModelForCausalLM.from_pretrained("microsoft/Phi-3-mini-4k-instruct", local_files_only=True)
        self.device = 0 if torch.cuda.is_available() else -1
        self.pipeline = pipeline("text-generation", model=self.model, tokenizer=self.tokenizer, device=self.device)

    def predict(self, data):
        prompt = self.format_sensor_data(data)
        try:
            result = self.pipeline(prompt, max_length=150, num_return_sequences=1)[0]["generated_text"]
            logger.info(f"Phi3MiniModel prediction: {result}")
            return {sensor: {"summary": result} for sensor in data} if data else {"unknown": {"summary": result}}
        except Exception as e:
            logger.error(f"Phi3MiniModel prediction failed: {e}")
            return {sensor: {"summary": ""} for sensor in data} if data else {"unknown": {"summary": ""}}
class Llama3Model(SensorModel):
    def __init__(self):
        logger.info("Initializing Llama3Model...")
        self.tokenizer = AutoTokenizer.from_pretrained(
            "meta-llama/Llama-3-8B-Instruct",
            local_files_only=True,
            cache_dir=CACHE_DIR,
            token=os.getenv("HF_TOKEN")  # Required for gated access
        )
        self.model = AutoModelForCausalLM.from_pretrained(
            "meta-llama/Llama-3-8B-Instruct",
            local_files_only=True,
            cache_dir=CACHE_DIR,
            token=os.getenv("HF_TOKEN")
        )
        self.device = 0 if torch.cuda.is_available() else -1
        self.pipeline = pipeline("text-generation", model=self.model, tokenizer=self.tokenizer, device=self.device)

    def predict(self, data):
        prompt = self.format_sensor_data(data)
        try:
            result = self.pipeline(prompt, max_length=150, num_return_sequences=1)[0]["generated_text"]
            logger.info(f"Llama3Model prediction: {result}")
            return {sensor: {"summary": result} for sensor in data} if data else {"unknown": {"summary": result}}
        except Exception as e:
            logger.error(f"Llama3Model prediction failed: {e}")
            return {sensor: {"summary": ""} for sensor in data} if data else {"unknown": {"summary": ""}}