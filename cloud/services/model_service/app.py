# app.py
from flask import Flask, request, jsonify
from openai import OpenAI
import logging

app = Flask(__name__)

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

# Initialize OpenAI client
client = OpenAI(
    api_key='docker',
    base_url='http://host.docker.internal:12434/engines/llama.cpp/v1',
    timeout=200,  # Set a timeout for requests  
    )

@app.route('/health', methods=['GET'])
def health():
    """Return health status."""
    return jsonify({"status": "ok"})

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
                {"role": "system", "content": "You are a weatherman. summarize the weather conditions based on the sensor data provided in easy to understand language, and provide practical advice. Do not hallucinate data. Do not assume what time of the day it is, so do not say good morning, afternoon, evening or night. Do not hallucinate data. if you have no data just say that you have no data to analyze. Everything should  be less than 100 words"},
                {"role": "user", "content": prompt}
            ]
        )
        
        result = response.choices[0].message.content
        
        logger.info(f"Prediction successful({model}): {result}")
        return jsonify({"result": result}), 200
        
    except Exception as e:
        logger.error(f"Prediction failed: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5002)
