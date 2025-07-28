import yaml
import requests
import asyncio
from orchestrator import OrchestrateData
from logger import CustomLogger
from utils import Config

console = CustomLogger(name="mqtt_logs", log_dir="/cloud/logs")

class Application:
    def __init__(self, config: Config):
        self.orchestrator = OrchestrateData(logger=console, config=config)

    async def run(self):
        await self.orchestrator.initialize()
        await self.orchestrator.listen_and_store_readings()

if __name__ == "__main__":
    async def main():
        try:
            config = Config()
            app = Application(config)
            await app.run()

        except requests.exceptions.Timeout:
            console.exception("The request timed out")
        except requests.exceptions.ConnectionError as e:
            console.exception(f"Failed to connect to the server: {e}")
        except requests.exceptions.HTTPError as e:
            console.exception(f"HTTP error occurred: {e}")
        except requests.exceptions.JSONDecodeError as e:
            console.exception(f"Response was not valid JSON. {e}")
        except requests.exceptions.RequestException as e:
            console.exception(f"An unexpected request error occurred: {e}")
        except Exception as e:
            console.exception(f"General error occurred: {e}")

    asyncio.run(main())
