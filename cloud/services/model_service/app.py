# app.py
from flask import Flask, request, jsonify
from openai import OpenAI
import time
import logging
import os

app = Flask(__name__)

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

# Initialize OpenAI client
client = OpenAI(
    api_key='docker',
    base_url='http://host.docker.internal:12434/engines/llama.cpp/v1',
    timeout=50,  # Set a timeout for requests  
    )

# Model configuration
MODEL_NAME = "ai/smollm2"

@app.route('/health', methods=['GET'])
def health():
    """Return health status."""
    return jsonify({"status": "ok", "model": MODEL_NAME})

@app.route('/predict', methods=['POST'])
def predict():
    try:
        data = request.get_json()
        if not data or "data" not in data:
            logger.warning("Invalid request format received")
            return jsonify({"error": "Invalid request format, requires 'data' field"}), 400
        
        prompt = data["data"]
        model = data["model"]
        
        logger.info(f"Processing prediction with prompt: {prompt}")
        
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are a weatherman. summarize the weather conditions based on the sensor data provided and provide practical advice."},
                {"role": "user", "content": prompt}
            ]
        )
        
        result = response.choices[0].message.content
        
        logger.info(f"Prediction successful: {result}")
        return jsonify({"result": result}), 200
        
    except Exception as e:
        logger.error(f"Prediction failed: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)